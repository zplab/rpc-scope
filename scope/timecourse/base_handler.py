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
import inspect
import concurrent.futures as futures
import os

from zplib import util

from ..util import threaded_image_io
from ..util import log_util

class DummyIO:
    def __init__(self, logger):
        self.logger = logger
    def write(*args, **kws):
        self.logger.warning('Trying to write files, but file writing was disabled!')

class TimepointHandler:
    IMAGE_COMPRESSION = threaded_image_io.COMPRESSION.DEFAULT
    LOG_LEVEL = logging.INFO
    IO_THREADS = 4

    def __init__(self, data_dir, log_level=None, scope_host='127.0.0.1', dry_run=False):
        """Setup the basic code to take a single timepoint from a timecourse experiment.

        Parameters:
            data_dir: directory where the data and metadata-files should be read/written.
            io_threads: number of threads to use to save image data out.
            loglevel: level from logging library at which to log information to the
                logfile in data_dir. (Subclasses can log information with self.logger)
                If not specified, fall back to the class attribute LOG_LEVEL. This
                allows a subclass to set a default log level, which still can be
                over-ridden from the command line.
            scope_host: IP address to connect to the scope server. If None, run without
                a scope server.
            dry_run: if True, do not write any files (including log files; log entries
                will be printed to the console).
        """
        self.data_dir = pathlib.Path(data_dir)
        self.experiment_metadata_path = self.data_dir / 'experiment_metadata.json'
        with self.experiment_metadata_path.open('r') as f:
            self.experiment_metadata = json.load(f)
        self.positions = self.experiment_metadata['positions'] # dict mapping names to (x,y,z) stage positions
        self.skip_positions = set(self.experiment_metadata.setdefault('skip_positions', []))
        if scope_host is not None:
            from .. import scope_client
            self.scope, self.scope_properties = scope_client.client_main(scope_host)
            if hasattr(self.scope, 'camera'):
                self.scope.camera.return_to_default_state()
        else:
            self.scope = None
        self.write_files = not dry_run
        self.logger = log_util.get_logger(str(data_dir))
        if log_level is None:
            log_level = self.LOG_LEVEL
        elif isinstance(log_level, str):
            log_level = getattr(logging, log_level)
        self.logger.setLevel(log_level)
        if self.write_files:
            self.image_io = threaded_image_io.ThreadedIO(self.IO_THREADS)
            handler = logging.FileHandler(str(self.data_dir/'acquisitions.log'))
        else:
            self.image_io = DummyIO(self.logger)
            handler = logging.StreamHandler()
        handler.setFormatter(log_util.get_formatter())
        self.logger.addHandler(handler)
        self._job_thread = futures.ThreadPoolExecutor(max_workers=1)

    def _heartbeat(self):
        print('heartbeat') # write a line to stdout to serve as a heartbeat

    def run_timepoint(self, scheduled_start):
        try:
            self._heartbeat()
            self.timepoint_prefix = time.strftime('%Y-%m-%dt%H%M')
            self.scheduled_start = scheduled_start
            self.start_time = time.time()
            self._job_futures = []
            self.logger.info('Starting timepoint {} ({:.0f} minutes after scheduled)', self.timepoint_prefix,
                (self.start_time-self.scheduled_start)/60)
            # record the timepoint prefix and timestamp for this timepoint into the
            # experiment metadata
            self.experiment_metadata.setdefault('timepoints', []).append(self.timepoint_prefix)
            self.experiment_metadata.setdefault('timestamps', []).append(self.start_time)
            self.configure_timepoint()
            self._heartbeat()
            for position_name, position_coords in sorted(self.positions.items()):
                if position_name not in self.skip_positions:
                    self.run_position(position_name, position_coords)
                    self._heartbeat()
            self.experiment_metadata['skip_positions'] = list(self.skip_positions)
            self.finalize_timepoint()
            self._heartbeat()
            self.end_time = time.time()
            self.experiment_metadata.setdefault('durations', []).append(self.end_time - self.start_time)
            if self.write_files:
                self._write_atomic_json(self.experiment_metadata_path, self.experiment_metadata)
            run_again = self.skip_positions != self.positions.keys() # don't run again if we're skipping all the positions
            if self._job_futures:
                self.logger.debug('Waiting for background jobs')
                t0 = time.time()
                # wait for all queued background jobs to complete.
                not_done = self._job_futures
                while not_done:
                    # send heartbeats while we wait for futures to finish
                    done, not_done = futures.wait(not_done, timeout=60)
                    self._heartbeat()
                # now get the result() from each future, which will raise any errors encountered
                # during the execution.
                [f.result() for f in self._job_futures]
                self.logger.debug('Background jobs complete ({:.1f} seconds)', time.time()-t0)
            self.logger.info('Timepoint {} ended ({:.0f} minutes after starting)', self.timepoint_prefix,
                             (time.time()-self.start_time)/60)
            if run_again:
                return self.get_next_run_time()
        except:
            self.logger.error('Exception in timepoint:', exc_info=True)
            raise

    def add_background_job(self, function, *args, **kws):
        """Add a function with parameters *args and **kws to a queue to be completed
        asynchronously with the rest of the timepoint acquisition. This will be
        run in a background thread, so make sure that the function acts in a
        threadsafe manner. (NB: self.logger *is* thread-safe.)

        All queued functions will be waited for completion before the timepoint
        ends. Any exceptions will be propagated to the foreground after all
        functions queued either finish or raise an exception.
        """
        self._job_futures.append(self._job_thread.submit(function, *args, **kws))

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
        self.logger.info('Acquiring Position: {}', position_name)
        t0 = time.time()
        position_dir = self.data_dir / position_name
        position_dir.mkdir(exist_ok=True)
        metadata_path = position_dir / 'position_metadata.json'
        if metadata_path.exists():
            with metadata_path.open('r') as f:
                position_metadata = json.load(f)
        else:
            position_metadata = []
        timestamp = time.time()

        if self.scope is not None:
            self.scope.stage.position = position_coords
        t1 = time.time()
        self.logger.debug('Stage Positioned ({:.1f} seconds)', t1-t0)
        images, image_names, new_metadata = self.acquire_images(position_name, position_dir,
            position_metadata)
        t2 = time.time()
        self.logger.debug('{} Images Acquired ({:.1f} seconds)', len(images), t2-t1)
        image_paths = [position_dir / (self.timepoint_prefix + ' ' + name) for name in image_names]
        if new_metadata is None:
            new_metadata = {}
        new_metadata['timestamp'] = timestamp
        new_metadata['timepoint'] = self.timepoint_prefix
        position_metadata.append(new_metadata)
        if self.write_files:
            self.image_io.write(images, image_paths, self.IMAGE_COMPRESSION)
            self._write_atomic_json(metadata_path, position_metadata)
        t3 = time.time()
        self.logger.debug('Images saved ({:.1f} seconds)', t3-t2)
        self.logger.debug('Position done (total: {:.1f} seconds)', t3-t0)

    def _write_atomic_json(self, out_path, data):
        util.json_encode_atomic_legible_to_file(data, out_path, suffix=self.timepoint_prefix)

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

    @classmethod
    def main(cls, timepoint_dir=None, **cls_init_args):
        """Main method to run a timepoint.

        Parse sys.argv to find an (optional) scheduled_start time as a positional
        argument. Any arguments that contain an '=' will be assumed to be
        python variable definitions to pass to the class init method. (Leading
        '-' or '--' will be stripped, and internal '-'s will be converted to '_'.)

        e.g. this allows the following usage: ./acquire.py --dry-run=True --log-level=logging.DEBUG

        Parameters:
            timepoint_dir: location of timepoint directory. If not specified, default
                to the parent dir of the file that defines the class that this
                method is called on.
            **cls_init_args: dict of arguments to pass to the class init method.
        """
        if timepoint_dir is None:
            timepoint_dir = pathlib.Path(inspect.getfile(cls)).parent
        scheduled_start = None
        for arg in sys.argv[1:]:
            if arg.count('='):
                while arg.startswith('-'):
                    arg = arg[1:]
                arg = arg.replace('-', '_')
                # execute the argument in a restricted namespace containing only 'logging', and store the
                # result in the args to pass to the class.
                exec(arg, dict(logging=logging), cls_init_args)
            elif scheduled_start is None:
                scheduled_start = float(arg)
            else:
                raise ValueError('More than one schedule start time provided')

        if scheduled_start is None:
            scheduled_start = time.time()
        handler = cls(timepoint_dir, **cls_init_args)
        next_run_time = handler.run_timepoint(scheduled_start)
        if next_run_time:
            print('next run:{}'.format(next_run_time))

