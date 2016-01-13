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

import collections
from ..config import scope_configuration

ExposureStep = collections.namedtuple('ExposureStep', ['exposure_ms', 'tl_enabled', 'tl_intensity', 'fl_enabled', 'delay_after_ms', 'on_delay_ms', 'off_delay_ms'])

class AcquisitionSequencer:
    def __init__(self, scope):
        self._camera = scope.camera
        self._iotool = scope.iotool
        self._spectra_x = scope.il.spectra_x
        self._tl_lamp = scope.tl.lamp
        self._config = scope_configuration.get_config()
        self._latest_timestamps = None
        self._exposures = None
        self._compiled = False
        self._num_acquisitions = 0

    def new_sequence(self, **fl_intensities):
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
        self._exposures = None
        self._compiled = False
        # starting state is with all the spectra x lamps off
        lamp_names = self._spectra_x.get_lamp_specs() # returns a dict
        self._starting_fl_lamp_state = {lamp+'_enabled': False for lamp in lamp_names}
        # set lamps to the requested intensity, or 255 for lamps not specified
        for lamp in lamp_names:
            intensity = fl_intensities.get(lamp, 255)
            self._starting_fl_lamp_state[lamp+'_intensity'] = intensity
        self._latest_timestamps = None

    def _add_delay(self, delay_ms):
        if delay == 0:
            return []
        assert 0.004 <= delay_ms <= 2**15-1
        delay_us = int(delay_ms * 1000)
        steps = []
        if delay_us < 2**15: # the most the microsecond counter can count to is 2**15-1 (32767)
            us = delay_us
            ms = 0
        else:
            us = delay_us % 1000
            ms = delay_us // 1000
            # delay_ms command takes 15 microseconds to run. Subtract this off.
            # The easiest thing to do is just to lop off 1 full ms and add that back
            # as an additional 985 us delay, plus the 15 to do the time to run delay_ms.
            # This way, we also know that us is always > 4, so that we won't have a problem
            # with the fact that delay_us takes 4 us to run...
            ms -= 1
            us += 985
            steps.append(self._iotool.commands.delay_ms(ms))
        # Note: there will always be a us delay, and that we know it will be >= 4
        # delay_us takes 4 us to run. Subtract that off.
        steps.append(self._iotool.commands.delay_us(us-4))
        return steps

    def add_step(self, exposure_ms, tl_enabled=False, tl_intensity=None, fl_enabled=False, delay_after_ms=0):
        """Add an image acquisition step to the existing sequence.

        Parameters
        exposure_ms: exposure time in ms for the image.
        tl_enabled: True/False for whether the transmitted lamp should be enabled.
        tl_intensity: intensity of the transmitted lamp, should it be enabled.
          If none, then do not change intensity setting from current value.
        fl_enabled: list of spectra x lamps to enable, or string for a single lamp.
          NB: Either tl_enabled must be True or fl_enabled must be non-empty/non-False
        delay_after_ms: time to delay after turning off the lamps but before triggering
          the next acquisition.
        """
        self._compiled = False
        if tl_enabled and fl_enabled:
            raise ValueError('Only the TL lamp OR one or more Spectra X lamps can be enabled, not both.')
        if not (tl_enabled or fl_enabled):
            raise ValueError('Either the TL lamp OR one or more Spectra X lamps must be enabled.')
        if tl_enabled:
            lamp_timing = self._config.IOTool.TL_TIMING
        else:
            if isinstance(fl_enabled, str):
                fl_enabled = [fl_enabled]
            lamp_timing = self._config.IOTool.SPECTRA_X_TIMING
        # Now, calculate the exposure timing: how long to delay after turning the lamp on, and
        # how long to delay after turning the lamp off.
        # The on-delay is not just the exposure time: we need to account for latency between
        # sending the lamp-on/off signal and the intensity actually starting to change,
        # and we need to account for the fact that the lamp has a rise/fall time.
        # So when turning on the lamp, we wait for the on-latency, the rise time,
        # and the amount of time the lamp needs to be fully on, minus the off-latency.
        # After turning off the lamp, we wait for the off-latency, the fall time, and
        # then any additional requested delay.
        # The fully-on time is not the exposure time either, because the lamp intensity rises and falls
        # during the exposure (and not before and after). During rise/fall the lamp is on average only
        # half as bright. So if the rise time is 4 ms and the fall time is 2 ms, then over those
        # 6 ms, only the eqivalent of 3 ms of luminous flux is put out (compared to a fully-on lamp).
        # So, if the user requests a 3 ms exposure, the 6 ms of rise and fall are all that is needed
        # for "3 ms" worth of light. If the  user requests a 4 ms exposure, that should be 6 ms of
        # rise/fall + 1 ms full-on.
        # To get the length of the full-on exposure required, subtract half of (rise + fall time)
        # from the requested exposure time. Raise an error if a shorter exposure than
        # (rise + fall) / 2 + off-latency is requested.
        half_rise_fall = (lamp_timing.rise_ms + lamp_timing.fall_ms) / 2
        min_exp = half_rise_fall + lamp_timing.off_latency_ms
        if exposure_ms < min_exp:
            raise ValueError('Minimum exposure time given lamp timing data is {}'.format(min_exp))
        full_on_time = exposure_ms - half_rise_fall
        on_delay_ms = lamp_timing.on_latency_ms + lamp_timing.rise_ms + full_on_time - lamp_timing.off_latency_ms
        off_delay_ms = lamp_timing.off_latency_ms + lamp_timing.fall_ms + delay_after_ms
        self._steps.append(ExposureStep(exposure_ms, tl_enabled, tl_intensity, fl_enabled, delay_after_ms, on_delay_ms, off_delay_ms))

    def _compile(self):
        """Send the acquisition sequence to the IOTool box"""
        if self._compiled:
            return
        if len(self._steps) == 0:
            raise RuntimeError('No acquisition steps have been configured')
        iotool_steps = []
        self._fire_all_time = [] # contains the total time for each step that the camera is in "fire all" mode. This plus the readout time is the actual exposure time (for dark current calculations)
        commands = self._iotool.commands
        io_config = self._config.IOTool
        iotool_steps.append(commands.wait_time(20)) # configure a 20 microsecond debounce-wait for high/low signals to stabilize
        iotool_steps.append(commands.wait_high(io_config.CAMERA_PINS.arm))
        for step in self._steps:
            iotool_steps.append(commands.set_high(io_config.CAMERA_PINS.trigger)) # trigger a camera acquisition
            iotool_steps.append(commands.set_low(io_config.CAMERA_PINS.trigger))
            # wait until all rows are exposing, reported by the camera's FireAll signal
            # Sometimes it takes a moment for the FireAll signal to clear after the trigger, so delay 50 us before waiting for FireAll
            iotool_steps += self._add_delay(0.05)
            iotool_steps.append(commands.wait_high(io_config.CAMERA_PINS.aux_out1)) # AuxOut1 is set to 'FireAll'
            # Now turn on the required lamp (either TL or Spectra X)
            if step.tl_enabled:
                iotool_steps.extend(commands.transmitted_lamp(enabled=True, intensity=step.tl_intensity))
            else:
                iotool_steps.extend(commands.spectra_x_lamps(**{lamp:True for lamp in step.fl_enabled}))
            # wait the required amount of time for the lamp to turn on and expose the image (as calculated in add_step)
            iotool_steps += self._add_delay(step.on_delay_ms)
            # Now turn off the lamp.
            if step.tl_enabled:
                iotool_steps.extend(commands.transmitted_lamp(enabled=False))
            else:
                iotool_steps.extend(commands.spectra_x_lamps(**{lamp:False for lamp in step.fl_enabled}))
            # Now wait for the lamp to go off, plus any extra requested delay.
            iotool_steps += self._add_delay(step.off_delay_ms)
            self._fire_all_time.append(step.on_delay_ms + step.off_delay_ms)

        # send one last trigger to end the final acquisition
        iotool_steps.append(commands.set_high(io_config.CAMERA_PINS.trigger))
        iotool_steps.append(commands.set_low(io_config.CAMERA_PINS.trigger))
        self._iotool.store_program(*iotool_steps)
        self._compiled = True
        self._iotool_program = iotool_steps

    def get_iotool_program(self):
        self._compile()
        return self._iotool_program

    def get_steps(self):
        return self._steps

    def run(self):
        """Run the assembled acquisition steps and return the images obtained."""
        self._compile()
        # state stack: set tl_intensity to current intensity, so that if it gets set
        # as part of the acquisition, it will be returned to the current value. Must set it to
        # the current value here because if it's not set, setting it to something else
        # is the wrong thing to do.
        num_images = len(self._steps)
        safe_images = self._camera.get_safe_image_count_to_queue()
        if num_images > safe_images:
            raise RuntimeError('Camera cannot queue more than {} images in its current state, {} acquisition steps requested.'.format(safe_images, num_images))
        self._camera.set_io_selector('Aux Out 1')
        self._camera.start_image_sequence_acquisition(num_images, trigger_mode='External Exposure',
            overlap_enabled=True, auxiliary_out_source='FireAll', selected_io_pin_inverted=False)
        try:
            with self._spectra_x.in_state(**self._starting_fl_lamp_state), self._tl_lamp.in_state(enabled=False, intensity=self._tl_lamp.get_intensity()):
                readout_ms = self._camera.get_readout_time() # get this after setting the relevant camera modes above
                self._exposures = [exp + readout_ms for exp in self._fire_all_time]
                self._iotool.start_program()
                names, self._latest_timestamps = [], []
                for exposure in self._exposures:
                    names.append(self._camera.next_image(read_timeout_ms=exposure+1000))
                    self._latest_timestamps.append(self._camera.get_latest_timestamp())
                self._output = self._iotool.wait_until_done()
        finally:
            self._camera.end_image_sequence_acquisition()
        return names

    def get_latest_timestamps(self):
        return self._latest_timestamps

    def get_exposure_times(self):
        """Return the full amount of time the camera was exposing for each image.
        This is DIFFERENT than the 'exposure_ms' parameter to add_step. These
        exposure times also include the camera read time and any additional delays
        added in the middle of the acquisition.

        Exposures can only be retrieved AFTER the acquisition sequence is run.
        """
        return self._exposures

    def get_program_output(self):
        return self._output