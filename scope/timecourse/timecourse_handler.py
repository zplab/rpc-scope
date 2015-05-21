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
# Authors: Erik Hvatum <ice.rikh@gmail.com>, Zach Pincus <zpincus@wustl.edu>

import pathlib
import numpy
import inspect

from . import base_handler
from ..client_util import autofocus
from ..client_util import calibrate
from ..util import state_stack

class BasicAcquisitionHandler(base_handler.TimepointHandler):
    """Base class for most timecourse acquisition needs.

    To create a new timepoint acquisition, the user MUST subclass this class
    from a file that resides INSIDE the desired data-acquisition directory. An
    'experiment_metadata.json' file MUST be created in the same directory,
    containing a dict with keys 'positions', 'z_max', and
    'reference_positions'. The value of 'positions' MUST be a dict mapping
    position names to (x,y,z) stage coords for data acquisition. 'z_max' MUST
    be an single number representing the highest the stage can go during
    autofocus. 'reference_positions' MUST be a list of one or more (x,y,z)
    stage coords to obtain brightfield and fluorescence flatfield reference
    data from.

    The python file implementing the subclass MUST have the following stanza
    at the bottom:
        if __name__ == '__main__':
            MySubclass.main()
    where 'MySubclass' is replaced with whatever the name of the subclass is.

    The subclass MUST set the FILTER_CUBE attribute. In addition, if
    fluorescent flat-field images are desired the subclass MAY set
    FLUORESCENCE_FLATFIELD_LAMP to the name of a spectra X lamp that is
    compatible with the selected filter cube. Other class attributes MAY be set
    as desired; RUN_INTERVAL_MINUTES is of particular note.

    The subclass MAY override configure_additional_acquisition_steps() to
    add additional image acquisitions (after the initial default brightfield
    acquisition). The base class docstring shows an example of adding a 200 ms
    GFP exposure, which also requires adding the name of the image file to save
    out to the self.image_names attribute.
    """

    # Attributes and functions subclasses MUST or MAY override are here:
    # First: Really important attributes to override
    FILTER_CUBE = 'Choose a filter cube!'
    FLUORESCENCE_FLATFIELD_LAMP = None # MAKE SURE THIS IS COMPATIBLE WITH THE FILTER CUBE!!!
    RUN_INTERVAL_MINUTES = 60*8

    # Next: Potentially useful attributes to override
    OBJECTIVE = 10
    COARSE_FOCUS_RANGE = 1
    COARSE_FOCUS_STEPS = 50
    # 1 mm distance in 50 steps = 20 microns/step. So we should be somewhere within 20-40 microns of the right plane after the above autofocus.
    # We want to get within 1-2 microns, so sweep over 100 microns with 75 steps.
    FINE_FOCUS_RANGE = 0.1
    FINE_FOCUS_STEPS = 75
    PIXEL_READOUT_RATE = '100 MHz'
    USE_LAST_FOCUS_POSITION = True

    def configure_additional_acquisition_steps(self):
        """Add more steps to the acquisition_sequencer's sequence as desired,
        making sure to also add corresponding names to the image_name attribute.
        For example, to add a 200 ms GFP acquisition, a subclass may override
        this as follows:
            def configure_additional_acquisition_steps(self):
                self.scope.camera.acquisition_sequencer.add_step(exposure_ms=200,
                    tl_enable=False, cyan=True)
                self.image_names.append('gfp.png')
        """
        pass

    # Internal implementation functions are below. Override with care.
    def configure_timepoint(self):
        self.logger.info('Configuring acquisitions')
        self.scope.async = False
        self.scope.il.shutter_open = True
        self.scope.tl.shutter_open = True
        self.scope.tl.condenser_retracted = False
        self.scope.il.filter_cube = self.FILTER_CUBE
        self.scope.nosepiece.magnification = self.OBJECTIVE
        self.scope.camera.sensor_gain = '16-bit (low noise & high well capacity)'
        self.configure_calibrations() # sets self.bf_exposure and self.tl_intensity
        self.scope.camera.acquisition_sequencer.new_sequence(readout_rate=self.PIXEL_READOUT_RATE)
        self.scope.camera.acquisition_sequencer.add_step(exposure_ms=self.bf_exposure,
            tl_enable=True, tl_intensity=self.tl_intensity, lamp_off_delay=25) # delay is in microseconds
        self.image_names = ['bf.png']
        self.configure_additional_acquisition_steps()

    def configure_calibrations(self):
        self.dark_corrector = calibrate.DarkCurrentCorrector(self.scope)
        ref_positions = self.experiment_metadata['reference positions']

        self.scope.stage.position = ref_positions[0]
        with state_stack.pushed_state(self.scope.tl.lamp, enable=True):
            calibrate.meter_exposure(self.scope, self.scope.tl.lamp)
            bf_avg = calibrate.get_averaged_images(self.scope, ref_positions,
                self.dark_corrector, frames_to_average=2)
        vignette_mask = calibrate.get_vignette_mask(bf_avg)
        bf_flatfield = calibrate.get_flat_field(bf_avg, vignette_mask)
        cal_image_names = ['vignette_mask.png', 'bf_flatfield.tif']
        cal_images = [vignette_mask.astype(numpy.uint8)*255, bf_flatfield]

        if self.FLUORESCENCE_FLATFIELD_LAMP:
            self.scope.stage.position = ref_positions[0]
            lamp = getattr(self.scope.il.spectra_x, self.FLUORESCENCE_FLATFIELD_LAMP)
            with state_stack.pushed_state(lamp, enable=True):
                calibrate.meter_exposure(self.scope, lamp)
                fl_avg = calibrate.get_averaged_images(self.scope, ref_positions,
                    self.dark_corrector, frames_to_average=5)
            fl_flatfield = calibrate.get_flat_field(fl_avg, vignette_mask)
            cal_image_names.append('fl_flatfield.tif')
            cal_images.append(fl_flatfield)

        # go to a data-acquisition position and figure out the right brightfield exposure
        data_positions = self.experiment_metadata['positions']
        some_pos = list(data_positions.values())[0]
        self.scope.stage.position = some_pos
        self.bf_exposure, self.tl_intensity = calibrate.meter_exposure(self.scope, self.scope.tl.lamp)

        # save out calibration information
        calibration_dir = self.data_dir / 'calibrations'
        if not calibration_dir.exists():
            calibration_dir.mkdir()
        cal_image_paths = [position_dir / (self.timepoint_prefix + ' ' + name) for name in cal_names]
        self.image_io.write(cal_images, cal_image_paths)
        metering = self.experiment_metadata.setdefault('brightfield metering', {})
        metering[self.timepoint_prefix] = dict(exposure=self.bf_exposure, intensity=self.tl_intensity)


    def acquire_images(self, position_name, position_dir, timepoint_prefix, previous_timepoints, previous_metadata):
        if self.USE_LAST_FOCUS_POSITION and previous_metadata:
            z_start = previous_metadata[-1]['fine_z']
        else:
            x, y, z = self.positions[position_name]
            z_start = z
        z_max = self.experiment_metadata['z_max']
        coarse_z, fine_z = autofocus.autofocus(self.scope, z_start, z_max,
            self.COARSE_FOCUS_RANGE, self.COARSE_FOCUS_STEPS,
            self.FINE_FOCUS_RANGE, self.FINE_FOCUS_STEPS)

        self.logger.info('autofocus position: {}'.format(fine_z))
        images = self.scope.camera.acquisition_sequencer.run()
        exposures = self.scope.camera.acquisition_sequencer.exposure_times
        images = [self.dark_corrector.correct(image, exposure) for image, exposure in zip(images, exposures)]
        timestamps = numpy.array(self.scope.camera.acquisition_sequencer.latest_timestamps)
        timestamps = (timestamps - timestamps[0]) / self.scope.camera.timestamp_hz
        metadata = dict(coarse_z=coarse_z, fine_z=fine_z, image_timestamps=dict(zip(self.image_names, timestamps)))
        return images, self.image_names, metadata

    @classmethod
    def main(cls):
        data_dir = pathlib.Path(inspect.getfile(cls)).parent
        handler = cls(data_dir)
        base_handler.main(timepoint_function=handler.run_timepoint,
            next_run_interval=cls.RUN_INTERVAL_MINUTES*60, interval_mode='scheduled_start')
