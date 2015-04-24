import sys
import time
import pathlib
import json
import logging

from ..util import threaded_image_io
from ..util import log_util
from .. import scope_client

def main(timepoint_function, next_run_interval, interval_mode='scheduled_start'):
    """Main function designed to interact with the job running daemon, which
    starts a process with the timestamp of the scheduled start time as the first
    argument, and expects stdout to contain the timestamp of the next scheduled
    run-time.

    Arguments:
        timepoint_function: function to call to do whatever the job is supposed
            to do during its invocation. Usually it will be the run_timepoint
            method of a TimepointRunner subclass. If this function does not return
            True, the job will not be scheduled again.
        next_run_interval: in how many seconds should the job runner run this
            job again. (The beginning point of the interval is controlled by
            the 'interval_mode' parameter).
        interval_mode: one of 'scheduled_start', 'actual_start', 'end'. Selects
            what the starting time for the delay before the next run should be:
            when the job was scheduled to start, when it actually started,
            or when the job ends, respectively."""
    assert interval_mode in {'scheduled_start', 'actual_start', 'end'}
    scheduled_start = sys.argv[1]
    actual_start = time.time()
    run_again = timepoint_function()
    if run_again:
        end = time.time()
        if interval_mode == 'scheduled_start':
            start = float(scheduled_start)
        elif interval_mode == 'actual_start':
            start = actual_start
        else:
            start = end
        print(start+next_run_interval)

class TimepointRunner:
    def __init__(self, data_dir, io_threads=4, loglevel=logging.INFO, scope_host='127.0.0.1'):
        self.data_dir = pathlib.Path(data_dir)
        self.experiment_metadata_path = self.data_dir / 'experiment_metadata.json'
        with self.experiment_metadata_path.open('r') as f:
            self.experiment_metadata = json.load(f)
        self.positions = self.experiment_metadata['positions'] # dict mapping names to (x,y,z) stage positions
        if 'skip_positions' not in self.experiment_metadata:
            # add in this metadata entry, which will be saved out later in finalize_timepoint()
            self.experiment_metadata['skip_positions'] = []
        self.skip_positions = set(self.experiment_metadata['skip_positions'])
        self.scope = scope_client.rpc_client_main(scope_host)
        self.image_io = threaded_image_io.ThreadedIO(io_threads)
        self.logger = log_util.get_logger(str(data_dir))
        self.logger.setLevel(loglevel)
        handler = logging.FileHandler(str(self.data_dir/'acquisitions.log'))
        handler.setFormatter(log_util.get_formatter())
        self.logger.addHandler(handler)

    def run_timepoint(self):
        self.logger.info('Starting timepoint')
        self.configure_timepoint()
        for position_name, position_coords in sorted(self.positions.items()):
            if position_name not in self.skip_positions:
                self.run_position(position_name, position_coords)
        self.experiment_metadata['skip_positions'] = list(self.skip_positions)
        run_again = self.finalize_timepoint()
        with self.experiment_metadata_path.open('w') as f:
            self.experiment_metadata = json.dump(self.experiment_metadata, f)
        if self.skip_positions == self.positions.keys():
            # all positions are being skipped. Return False to tell the caller
            # that this job should not be re-scheduled.
            return False
        else:
            return True

    def configure_timepoint(self):
        """Override this method with global configuration for the image acquisitions
        (e.g. camera configuration). Member variables 'scope', 'experiment_metadata', and
        'positions' may be specifically useful."""
        pass

    def finalize_timepoint(self):
        """Override this method with global finalization after the images have been
        acquired for each position. Useful for altering the self.experiment_metadata
        dictionary before it is saved out.

        Note that positions added to self.skip_positions are automatically added
        to the metadata, so it is unnecessary to do this here.
        """

    def run_position(self, position_name, position_coords):
        self.logger.info('Acquiring position {} at {}', position_name, position_coords)
        position_dir = self.data_dir / position_name
        if not position_dir.exists():
            position_dir.mkdir()
        metadata_path = position_dir / 'position_metadata.json'
        if metadata_path.exists():
            with metadata_path.open('r') as f:
                position_metadata = json.load(f)
        else:
            position_metadata = {'timepoints':[], 'values':[]}
        timepoint_prefix = time.strftime('%Y-%m-%dt%H%M')
        timestamp = time.time()

        self.scope.stage.position = position_coords
        previous_timepoints = position_metadata['timepoints']
        previous_metadata = position_metadata['values']
        images, image_names, new_metadata = self.acquire_images(position_name, position_dir,
            timepoint_prefix, previous_timepoints, previous_metadata)
        image_paths = [position_dir / (timepoint_prefix + ' ' + name) for name in image_names]
        self.image_io.write(images, image_paths)
        if new_metadata is None:
            new_metadata = {}
        new_metadata['timestamp'] = timestamp
        position_metadata['timepoints'].append(timepoint_prefix)
        position_metadata['values'].append(new_metadata)
        with metadata_path.open('w') as f:
             json.dump(position_metadata, f)

    def acquire_images(self, position_name, position_dir, timepoint_prefix, previous_timepoints, previous_metadata):
        """Override this method in a subclass to define the image-acquisition sequence.

        All most subclasses will need to do is return the following as a tuple:
        (images, image_names, new_metadata), where:
            images is a list of the acquired images
            image_names is a list of the generic names for each of these images
                (not timepoint- or position-specific; e.g. 'GFP.png' or some such)
            new_metadata is a dictionary of timepoint-specific information, such
                as the latest focal plane z-position or similar. This will be
                made available to future acquisition runs via the 'position_metadata'
                argument described below.

        The images and metadata will be written out by the superclass, and
        must not be written by the overriding subclass.

        Optionally, subclasses may choose to enter 'position_name' into the
        self.skip_positions set to indicate that in the future this position
        should not be acquired. (E.g. the worm is dead.)

        Arguments:
            position_name: identifier for this image-acquisition position. Useful
                for adding this position to the skip_positions set.
            position_dir: pathlib.Path object representing the directory where
                position-specific data files and outputs should be written. Useful
                only if additional data needs to be read in or out during
                acquisition. (E.g. a background model or similar.)
            timepoint_prefix: name with which any output files from this
                acquisition run should be prefixed. Useful only if additional
                timepoint-specific data needs to be written out by this function.
            previous_timepoints: list of all the prior 'timepoint_prefix' values
                for this position, in chronological order.
            previous_metadata: list of all the stored position metadata from the
                previous timepoints, in chronological order. In particular, this
                dictionary is guaranteed to contain 'timestamp' which is the
                time.time() at which that acquisition was started. Other values
                (such as the latest focal plane) stored by previous acquisition
                runs will also be available. The most recent metadata will be in
                previous_metadata[-1].
        """
        raise NotImplementedError()


