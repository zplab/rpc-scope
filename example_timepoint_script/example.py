import sys
import pathlib
import numpy

from scope.timecourse import timecourse_script

class Runner(timecourse_script.TimepointRunner):
    def configure_timepoint(self):
        self.logger.info('configuring timepoint')

    def finalize_timepoint(self):
        self.logger.info('finalizing timepoint')

    def acquire_images(self, position_name, position_dir, timepoint_prefix, previous_timepoints, previous_metadata):
        self.logger.info('{}, {}', previous_timepoints, previous_metadata)
        images = [numpy.ones((10,10), dtype=numpy.uint8) for i in range(3)]
        image_names = ['sleepy.png', 'grumpy.png', 'dopey.png']
        new_metadata = {'foobar':numpy.random.random()}
        return images, image_names, new_metadata


class StubScope:
    def __init__(self):
        self.stage = self

runner = Runner(data_dir=pathlib.Path(__file__).parent, scope=StubScope())
timecourse_script.main(timepoint_function=runner.run_timepoint, next_run_interval=45, interval_mode='scheduled_start')