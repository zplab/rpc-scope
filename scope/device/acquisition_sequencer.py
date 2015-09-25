# The MIT License (MIT)
#
# Copyright (c) 2014 WUSTL ZPLAB
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

import time
import math

from ..config import scope_configuration

class AcquisitionSequencer:
    def __init__(self, scope):
        self._camera = scope.camera
        self._iotool = scope.iotool
        self._spectra_x = scope.il.spectra_x
        self._tl_lamp = scope.tl.lamp
        self._config = scope_configuration.get_config()
        self._latest_timestamps = None
        self._base_exposures = None
        self._exposures = None
        self._compiled = False
        self._num_acquisitions = 0

    def new_sequence(self, **spectra_x_intensities):
        """Create a new acquisition sequence of camera exposures with different
        lamps on and off.

        This sequence will place the camera in the mode best able to handle
        fast back-to-back image acquisitions with illumination and
        exposure-time changes in between each: rolling-shutter overlap
        external-exposure mode, where the IOTool box will send signals to tell
        the camera how long to expose for. The IOTool box will trigger start
        the exposure and wait for all of the image rows to start exposing (10
        or 27 ms, depending on readout rate, and signaled by the FireAll output
        from the camera going high). Once all rows are exposing, IOTool will
        turn on the desired lamps for the correct exposure time. Finally,
        IOTool will turn off the lamps and trigger the start of the next
        exposure. Because overlap mode is used, the sensor rows "roll off"
        after the acquisition at the same time as the rows "roll on" for the
        next acquisition. Thus, the "dead time" between frames is just a single
        frame-read time, which is the absolute minimum obtainable, especially
        in a mode where the exposure time can be set to any value at all.

        Note that for each image, the total exposure time will be the given
        exposure time plus the frame read time, though the lights will only be
        on for the given exposure time. Thus if correcting for dark currents,
        the former total exposure time should be used.

        Keyword Parameters: intensity values for the Spectra X lamps, if they
            are not to be used at full intensity. Any lamps not named will be
            set to full intensity.
        """
        self._steps = []
        self._base_exposures = [] # contains the actual exposure times that the camera is on, not just the length of time the light was on
        self._exposures = None
        self._compiled = False
        # set the wait time reasonably low because we have clean shielded cables
        self._steps.append(self._iotool.commands.wait_time(20))
        self._steps.append(self._iotool.commands.wait_high(self._config.IOTool.CAMERA_PINS['arm']))
        # turn off all the spectra x lamps
        lamp_names = self._spectra_x.get_lamp_specs().keys()
        self._starting_fl_lamp_state = {lamp+'_enabled': False for lamp in lamp_names}
        for lamp in lamp_names:
            intensity = spectra_x_intensities.get(lamp, 255)
            self._starting_fl_lamp_state[lamp+'_intensity'] = intensity
        self._num_acquisitions = 0
        self._latest_timestamps = None

    def add_delay_ms(self, delay):
        """Add a delay of the given number of milliseconds (up to 2**16) to the acquisition).
        Note that the camera will be exposing during this delay, though no lights will be on."""
        assert 0 < delay < 2**16
        self._steps.append(self._iotool.commands.delay_ms(int(delay)))
        self._base_exposures[-1] += delay

    def add_delay_us(self, delay):
        """Add a delay of the given number of microseconds (up to 2**15-1) to the acquisition).
        Note that the camera will be exposing during this delay, though no lights will be on.
        Note also that delays of 4 microseconds or less are not possible and the the delay
        will be 4 microseconds in this case."""
        assert 0 < delay < 2**15-1
        if delay < 4:
            delay = 4
        self._steps.append(self._iotool.commands.delay_us(int(delay)-4)) # delay command itself takes 4 us, so subtract off 4
        self._base_exposures[-1] += delay / 1000

    def add_step(self, exposure_ms, tl_enabled=None, tl_intensity=None, lamp_off_delay=None, **spectra_x_lamps):
        """Add an image acquisition step to the existing sequence.

        Parameters
        exposure_ms: exposure time in ms for the image.
        tl_enabled: should the transmitted lamp be on during the exposure?
        tl_intensity: intensity of the transmitted lamp, should it be enabled.
        lamp_off_delay: how long, in microseconds, to wait for the lamp to be completely
            off before starting the next acquisition.
        keywords: True/False enable values for the Spectra X lamps. Any lamps
        not named will be turned off.
        """
        self._compiled = False
        self._num_acquisitions += 1
        self._base_exposures.append(0) # the actual exposure time gets added in by the add_delay functions
        lamps = {lamp:True for lamp, value in spectra_x_lamps.items() if value}
        self._steps.append(self._iotool.commands.set_high(self._config.IOTool.CAMERA_PINS['trigger']))
        self._steps.append(self._iotool.commands.set_low(self._config.IOTool.CAMERA_PINS['trigger']))
        self.add_delay_us(50) # wait a little while for the FireAll signal to clear
        self._steps.append(self._iotool.commands.wait_high(self._config.IOTool.CAMERA_PINS['aux_out1'])) # set to 'FireAll'
        if tl_enabled:
            self._steps.extend(self._iotool.commands.transmitted_lamp(tl_enabled, tl_intensity))
        self._steps.extend(self._iotool.commands.spectra_x_lamps(**lamps))
        if lamp_off_delay:
            self.add_delay_us(lamp_off_delay)
        if exposure_ms < 32.767:
            self.add_delay_us(round(exposure_ms*1000))
        else:
            us, ms = math.modf(exposure_ms)
            us = int(round(us * 1000))
            self.add_delay_ms(ms)
            if us > 0:
                self.add_delay_us(us)
        if tl_enabled:
            self._steps.extend(self._iotool.commands.transmitted_lamp(enabled=False))
        self._steps.extend(self._iotool.commands.spectra_x_lamps(**{lamp:False for lamp in lamps})) # turn lamps back off
        if lamp_off_delay:
            self.add_delay_us(lamp_off_delay)

    def _compile(self):
        """Send the acquisition sequence to the IOTool box"""
        if self._compiled:
            return
        assert self._num_acquisitions > 0
        # send one last trigger to end the final acquisition
        steps = list(self._steps)
        steps.append(self._iotool.commands.set_high(self._config.IOTool.CAMERA_PINS['trigger']))
        steps.append(self._iotool.commands.set_low(self._config.IOTool.CAMERA_PINS['trigger']))
        self._iotool.store_program(*steps)
        self._compiled = True
        self._program = steps

    def get_program(self):
        self._compile()
        return self._program

    def run(self):
        """Run the assembled acquisition steps and return the images obtained."""
        self._compile()
        # state stack: set tl_intensity to current intensity, so that if it gets set
        # as part of the acquisition, it will be returned to the current value. Must set it to
        # the current value here because if it's not set, setting it to something else
        # is the wrong thing to do.

        self._camera.set_io_selector('Aux Out 1')
        self._camera.set_selected_io_pin_inverted(False)
        self._camera.start_image_sequence_acquisition(self._num_acquisitions, trigger_mode='External Exposure',
            overlap_enabled=True, auxiliary_out_source='FireAll')
        with self._spectra_x.in_state(**self._starting_fl_lamp_state), \
             self._tl_lamp.in_state(enabled=False, intensity=self._tl_lamp.get_intensity()):
            readout_ms = self._camera.get_readout_time() # get this after setting the relevant camera modes above
            self._exposures = [exp + readout_ms for exp in self._base_exposures]
            self._iotool.start_program()
            names, self._latest_timestamps = [], []
            for exposure in self._exposures:
                names.append(self._camera.next_image(read_timeout_ms=exposure+1000))
                self._latest_timestamps.append(self._camera.get_latest_timestamp())
            self._output = self._iotool.wait_until_done()
            self._camera.end_image_sequence_acquisition()
        return names

    def get_latest_timestamps(self):
        return self._latest_timestamps

    def get_exposure_times(self):
        """Return the full amount of time the camera was exposing for each image.
        This is DIFFERENT than the amount of time that the light was on at each step,
        which is the 'exposure_ms' parameter to add_step.

        Exposures can only be retrieved AFTER the acquisition sequence is run.

        These exposure times also include the camera read time and any additional delays
        added in the middle of the acquisition."""
        return self._exposures

    def get_program_output(self):
        return self._output
