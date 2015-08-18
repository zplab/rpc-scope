# The MIT License (MIT)
#
# Copyright (c) 2014-2015 WUSTL ZPLAB
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Authors: Zach Pincus

import sys
import time
import pathlib
import json
import logging

from ..util import json_encode
from ..util import threaded_image_io
from ..util import log_util

def main(timepoint_function):
    """Main function designed to interact with the job running daemon, which
    starts a process with the timestamp of the scheduled start time as the first
    argument, and expects stdout to contain the timestamp of the next scheduled
    run-time.

    Parameters:
        timepoint_function: function to call to do whatever the job is supposed
            to do during its invocation. Usually it will be the run_timepoint
            method of a TimepointHandler subclass. The function must return
            the number of seconds the job-runner should wait before running
            the job again. If None is returned, then the job will not be re-run.
            The scheduled starting timestamp will be passed to timepoint_function
            as a parameter.
    """
    if len(sys.argv) > 0:
        scheduled_start = float(sys.argv[1])
    else:
        scheduled_start = time.time()
    next_run_time = timepoint_function(scheduled_start)
    if next_run_time:
        print(next_run_time)

class TimepointHandler:
    def __init__(self, data_dir, io_threads=4, loglevel=logging.INFO, scope_host='127.0.0.1'):
        """Setup the basic code to take a single timepoint from a timecourse experiment.

        Parameters:
            data_dir: directory where the data and metadata-files should be read/written.
            io_threads: number of threads to use to save image data out.
            loglevel: level from logging library at which to log information to the
                logfile in data_dir. (Subclasses can log information with self.logger)
            scope_host: IP address to connect to the scope server. If None, run without
                a scope server.
        """
        self.data_dir = pathlib.Path(data_dir)
        self.experiment_metadata_path = self.data_dir / 'experiment_metadata.json'
        with self.experiment_metadata_path.open('r') as f:
            self.experiment_metadata = json.load(f)
        self.positions = self.experiment_metadata['positions'] # dict mapping names to (x,y,z) stage positions
        self.skip_positions = set(self.experiment_metadata.setdefault('skip_positions', []))
        if scope_host is not None:
            from .. import scope_client
            self.scope = scope_client.rpc_client_main(scope_host)
        else:
            self.scope = None
        self.image_io = threaded_image_io.ThreadedIO(io_threads)
        self.logger = log_util.get_logger(str(data_dir))
        self.logger.setLevel(loglevel)
        handler = logging.FileHandler(str(self.data_dir/'acquisitions.log'))
        handler.setFormatter(log_util.get_formatter())
        self.logger.addHandler(handler)

    def run_timepoint(self, scheduled_start):
        try:
            self.timepoint_prefix = time.strftime('%Y-%m-%dt%H%M')
            self.scheduled_start = scheduled_start
            self.start_time = time.time()
            self.logger.info('Starting timepoint {} ({:.0f} minutes after scheduled)', self.timepoint_prefix,
                (self.start_time-self.scheduled_start)/60)
            # record the timepoint prefix and timestamp for this timepoint into the
            # experiment metadata
            self.experiment_metadata.setdefault('timepoints', []).append(self.timepoint_prefix)
            self.experiment_metadata.setdefault('timestamps', []).append(self.start_time)
            self.configure_timepoint()
            for position_name, position_coords in sorted(self.positions.items()):
                if position_name not in self.skip_positions:
                    self.run_position(position_name, position_coords)
            self.experiment_metadata['skip_positions'] = list(self.skip_positions)
            self.finalize_timepoint()
            self.end_time = time.time()
            self.experiment_metadata.setdefault('durations', []).append(self.end_time - self.start_time)
            with self.experiment_metadata_path.open('w') as f:
                json_encode.encode_legible_to_file(self.experiment_metadata, f)
            run_again = self.skip_positions != self.positions.keys() # don't run again if we're skipping all the positions
            if run_again:
                return self.get_next_run_time()
        except:
            self.logger.error('Exception in timepoint:', exc_info=True)
            raise

    def configure_timepoint(self):
        """Override this method with global configuration for the image acquisitions
        (e.g. camera configuration). Member variables 'scope', 'experiment_metadata',
        'timepoint_prefix', and 'positions' may be specifically useful."""
        pass

    def finalize_timepoint(self):
        """Override this method with global finalization after the images have been
        acquired for each position. Useful for altering the self.experiment_metadata
        dictionary before it is saved out.

        Note that positions added to self.skip_positions are automatically added
        to the metadata, so it is unnecessary to do this here.
        """
        pass

    def get_next_run_time(self):
        """Override this method to return when the next timepoint run should be
        scheduled. Returning None means no future runs will be scheduled."""
        return None

    def run_position(self, position_name, position_coords):
        """Do everything required for taking a timepoint at a single position
        EXCEPT focusing / image acquisition. This includes moving the stage to
        the right x,y position, loading and saving metadata, and saving image
        data, as generated by acquire_images()"""
        self.logger.info('Acquiring position {} at {}', position_name, position_coords)
        position_dir = self.data_dir / position_name
        if not position_dir.exists():
            position_dir.mkdir()
        metadata_path = position_dir / 'position_metadata.json'
        if metadata_path.exists():
            with metadata_path.open('r') as f:
                position_metadata = json.load(f)
        else:
            position_metadata = []
        timestamp = time.time()

        if self.scope is not None:
            self.scope.stage.position = position_coords
        images, image_names, new_metadata = self.acquire_images(position_name, position_dir,
            position_metadata)
        image_paths = [position_dir / (self.timepoint_prefix + ' ' + name) for name in image_names]
        self.image_io.write(images, image_paths)
        if new_metadata is None:
            new_metadata = {}
        new_metadata['timestamp'] = timestamp
        position_metadata.append(new_metadata)
        with metadata_path.open('w') as f:
             json_encode.encode_legible_to_file(position_metadata, f)

    def acquire_images(self, position_name, position_dir, position_metadata):
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

        Parameters:
            position_name: identifier for this image-acquisition position. Useful
                for adding this position to the skip_positions set.
            position_dir: pathlib.Path object representing the directory where
                position-specific data files and outputs should be written. Useful
                only if additional data needs to be read in or out during
                acquisition. (E.g. a background model or similar.)
            position_metadata: list of all the stored position metadata from the
                previous timepoints, in chronological order. In particular, this
                dictionary is guaranteed to contain 'timestamp' which is the
                time.time() at which that acquisition was started. Other values
                (such as the latest focal plane) stored by previous acquisition
                runs will also be available. The most recent metadata will be in
                position_metadata[-1].
        """
        raise NotImplementedError()
