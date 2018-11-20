# This code is licensed under the MIT License (see LICENSE file for details)

import time
import collections
from ..config import scope_configuration
from . import andor
from . import iotool
from . import spectra
from . import tl_lamp

ExposureStep = collections.namedtuple('ExposureStep', ['exposure_ms', 'lamp', 'tl_intensity', 'delay_after_ms', 'on_delay_ms', 'off_delay_ms'])

class AcquisitionSequencer:
    def __init__(self, camera: andor.Camera, iotool: iotool.IOTool, spectra: spectra.SpectraX, tl_lamp: tl_lamp.SutterLED_Lamp):
        self._camera = camera
        self._iotool = iotool
        self._spectra = spectra
        self._tl_lamp = tl_lamp
        self._config = scope_configuration.get_config()
        self._exposures = None
        self._output = None
        self._iotool_program = None
        self._latest_timestamps = None
        self._lamp_names = set(self._spectra.get_lamp_specs())
        # starting state is with all the spectra lamps off
        self._default_fl_lamp_state = {}
        for lamp in self._lamp_names:
            self._default_fl_lamp_state[lamp+'_enabled'] = False
            self._default_fl_lamp_state[lamp+'_intensity'] = 255
        self.new_sequence()

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
        self._compiled = False
        if not self._lamp_names.issuperset(fl_intensities.keys()):
            raise ValueError('Unrecognized spectra lamp name. Valid names are: {}'.format(', '.join(sorted(self._lamp_names))))
        self._starting_fl_lamp_state = dict(self._default_fl_lamp_state)
        for lamp, intensity in fl_intensities.items():
            self._starting_fl_lamp_state[lamp+'_intensity'] = intensity
        self._fl_intensities = fl_intensities

    def add_step(self, exposure_ms, lamp, tl_intensity=None, delay_after_ms=0):
        """Add an image acquisition step to the existing sequence.

        Parameters
        exposure_ms: exposure time in ms for the image.
        lamp: 'TL' for transmitted light, or name of a spectra lamp for
            fluorescence (or a list of one or more spectra lamp names).
        tl_intensity: intensity of the transmitted lamp, should it be enabled.
            If None, then do not change intensity setting from current value.
        delay_after_ms: time to delay after turning off the lamps but before triggering
            the next acquisition.
        """
        self._compiled = False
        if lamp == 'TL':
            lamp_timing = self._config.sutter_led.TIMING
        else:
            if tl_intensity is not None:
                raise ValueError('Cannot control TL intensity when the requested lamp is not TL.')
            if isinstance(lamp, str):
                lamp = [lamp]
            if not self._lamp_names.issuperset(lamp):
                raise ValueError('Unrecognized spectra lamp name. Valid names are: {}'.format(', '.join(sorted(self._lamp_names))))
            lamp_timing = self._config.spectra.TIMING
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
        off_delay_ms = lamp_timing.off_latency_ms + lamp_timing.fall_ms
        self._steps.append(ExposureStep(exposure_ms, lamp, tl_intensity, delay_after_ms, on_delay_ms, off_delay_ms))

    def _compile(self):
        """Send the acquisition sequence to the IOTool box"""
        if self._compiled:
            return
        if len(self._steps) == 0:
            raise RuntimeError('No acquisition steps have been configured')
        iotool_steps = []
        self._fire_all_time = [] # contains the total time for each step that the camera is in "fire all" mode. This plus the readout time is the actual exposure time (for dark current calculations)
        commands = self._iotool.commands
        cam_config = self._config.camera
        iotool_steps.append(commands.wait_time(20)) # configure a 20 microsecond debounce-wait for high/low signals to stabilize
        iotool_steps.append(commands.wait_high(cam_config.IOTOOL_PINS.arm))
        for step in self._steps:
            iotool_steps.append(commands.set_high(cam_config.IOTOOL_PINS.trigger)) # trigger a camera acquisition
            iotool_steps.append(commands.set_low(cam_config.IOTOOL_PINS.trigger))
            # wait until all rows are exposing, reported by the camera's FireAll signal
            # Sometimes it takes a moment for the FireAll signal to clear after the trigger, so delay 50 us before waiting for FireAll
            iotool_steps += self._add_delay(0.05)
            iotool_steps.append(commands.wait_high(cam_config.IOTOOL_PINS.aux_out1)) # AuxOut1 is set to 'FireAll'
            # Now turn on the required lamp (either TL or Spectra X)
            if step.lamp == 'TL':
                iotool_steps.extend(self._tl_lamp._iotool_lamp_commands(enabled=True, intensity=step.tl_intensity))
            else:
                iotool_steps.extend(self._spectra._iotool_lamp_commands(**{lamp: True for lamp in step.lamp}))
            # wait the required amount of time for the lamp to turn on and expose the image (as calculated in add_step)
            iotool_steps += self._add_delay(step.on_delay_ms)
            # Now turn off the lamp.
            if step.lamp == 'TL':
                iotool_steps.extend(self._tl_lamp._iotool_lamp_commands(enabled=False))
            else:
                iotool_steps.extend(self._spectra._iotool_lamp_commands(**{lamp: False for lamp in step.lamp}))
            # Now wait for the lamp to go off, plus any extra requested delay.
            total_off_delay = step.off_delay_ms + step.delay_after_ms
            iotool_steps += self._add_delay(total_off_delay)
            self._fire_all_time.append(step.on_delay_ms + total_off_delay)

        # send one last trigger to end the final acquisition
        iotool_steps.append(commands.set_high(cam_config.IOTOOL_PINS.trigger))
        iotool_steps.append(commands.set_low(cam_config.IOTOOL_PINS.trigger))
        self._iotool.store_program(*iotool_steps)
        self._compiled = True
        self._iotool_program = iotool_steps

    def _add_delay(self, delay_ms):
        if delay_ms == 0:
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

    def get_iotool_program(self):
        self._compile()
        return self._iotool_program

    def get_steps(self):
        steps = []
        for step in self._steps:
            add_step_args = {arg: getattr(step, arg) for arg in ['exposure_ms', 'lamp', 'tl_intensity', 'delay_after_ms']}
            steps.append(add_step_args)
        return dict(custom_intensities=self._fl_intensities, steps=steps)

    def set_steps(self, step_dict):
        self.new_sequence(**step_dict.get('custom_intensities', {}))
        for add_step_args in step_dict['steps']:
            self.add_step(**add_step_args)
        self._compile()

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
        config = self._config
        camera_state = dict(trigger_mode='External Exposure', overlap_enabled=True, auxiliary_out_source='FireAll', selected_io_pin_inverted=False)
        with self._camera.image_sequence_acquisition(num_images, **camera_state), \
             self._spectra.in_state(**self._starting_fl_lamp_state), \
             self._tl_lamp.in_state(enabled=False, intensity=self._tl_lamp.get_intensity()):
            # wait for lamps to turn off
            time.sleep(max(config.sutter_led.TIMING.off_latency_ms + config.sutter_led.TIMING.fall_ms,
                           config.spectra.TIMING.off_latency_ms + config.spectra.TIMING.fall_ms) / 1000)
            readout_ms = self._camera.get_readout_time() # get this after setting the relevant camera modes above
            self._exposures = [exp + readout_ms for exp in self._fire_all_time]
            self._iotool.start_program()
            names, self._latest_timestamps = [], []
            for exposure in self._exposures:
                name, timestamp, frame = self._camera.next_image_and_metadata(read_timeout_ms=exposure+1000)
                names.append(name)
                self._latest_timestamps.append(timestamp)
            self._output = self._iotool.wait_until_done()
        return names

    def get_latest_timestamps(self):
        return self._latest_timestamps

    def get_exposure_times(self):
        """Return the full amount of time the camera was exposing for each image.
        This is DIFFERENT than the 'exposure_ms' parameter to add_step. These
        exposure times also include the camera read time and any additional delays
        added in the middle of the acquisition.
        """
        self._compile()
        return self._exposures

    def get_program_output(self):
        return self._output
