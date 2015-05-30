import sys
import pathlib
import numpy

try:
    from scope.timecourse import timecourse_handler
except:
    # scopy package not installed... try seeing if it's running in place in the repo
    sys.path.append(str(pathlib.Path(__file__).parent.parent))
    from scope.timecourse import timecourse_handler

class Handler(timecourse_handler.TimepointHandler):
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

handler = Handler(data_dir=pathlib.Path(__file__).parent, scope_host=None)
timecourse_handler.main(timepoint_function=handler.run_timepoint, next_run_interval=45, interval_mode='scheduled_start')