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

import time

from ..config import scope_configuration

class AcquisitionSequencer:
    def __init__(self, camera, io_tool, spectra_x):
        self._camera = camera
        self._io_tool = io_tool
        self._spectra_x = spectra_x
        self._config = scope_configuration.get_config()

    def new_sequence(self, readout_rate='280 MHz', **spectra_x_intensities):
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

        Parameters
        readout_rate: '280 MHz' or '100 MHz', corresponding to the Andor camera's
            digitization rate. Slower = lower noise, but, longer dead-time between
            frames (27 ms vs. 10 ms.)
        keywords: intensity values for the Spectra X lamps, if they are not to
            be used at full intensity. Any lamps not named will be set to full
            intensity.
        """
        self._steps = []
        self._exposures = []
        self._compiled = False
        # set the wait time low because we have clean shielded cables
        self._steps.append(self._io_tool.commands.wait_time(2))
        # turn off all the spectra x lamps
        self._steps.extend(self._io_tool.commands.spectra_x_lamps(**{lamp:False for lamp in self._config.IOTool.LUMENCOR_PINS.keys()}))
        for lamp in self._config.IOTool.LUMENCOR_PINS.keys():
            if lamp not in spectra_x_intensities:
                spectra_x_intensities[lamp] = 255
        self._spectra_x_intensities = spectra_x_intensities
        self._readout_rate = readout_rate
        self._num_acquisitions = 0

    def add_step(self, exposure_ms, tl_enable=None, tl_intensity=None, **spectra_x_lamps):
        """Add an image acquisition step to the existing sequence.

        Parameters
        exposure_ms: exposure time in ms for the image.
        tl_enable: should the transmitted lamp be on during the exposure?
        tl_intensity: intensity of the transmitted lamp, should it be enabled.
        keywords: True/False enable values for the Spectra X lamps. Any lamps
        not named will be turned off.
        """
        self._compiled = False
        self._num_acquisitions += 1
        self._exposures.append(exposure_ms)
        lamps = {lamp:True for lamp, value in spectra_x_lamps.items() if value}
        self._steps.append(self._io_tool.commands.wait_high(self._config.IOTool.CAMERA_PINS['Arm']))
        self._steps.append(self._io_tool.commands.set_high(self._config.IOTool.CAMERA_PINS['Trigger']))
        self._steps.append(self._io_tool.commands.set_low(self._config.IOTool.CAMERA_PINS['Trigger']))
        self._steps.append(self._io_tool.commands.wait_high(self._config.IOTool.CAMERA_PINS['AuxOut1'])) # set to 'FireAll'
        self._steps.extend(self._io_tool.commands.transmitted_lamp(tl_enable, tl_intensity))
        self._steps.extend(self._io_tool.commands.spectra_x_lamps(**lamps))
        if exposure_ms <= 65.535:
            self._steps.append(self._io_tool.commands.delay_us(int(round(exposure_ms*1000))-4)) # delay command itself takes 4 µs, so subtract off 4
        else:
            self._steps.append(self._io_tool.commands.delay_ms(int(round(exposure_ms))))
        if tl_enable:
            self._steps.extend(self._io_tool.commands.transmitted_lamp(enable=False))
        self._steps.extend(self._io_tool.commands.spectra_x_lamps(**{lamp:False for lamp in lamps})) # turn lamps back off
        self._steps.append(self._io_tool.commands.delay_us(300)) # extra thick fudge for fall time of LEDs

    def _compile(self):
        """Send the acquisition sequence to the IOTool box"""
        assert self._num_acquisitions > 0
        # send one last trigger to end the final acquisition
        steps = list(self._steps)
        steps.append(self._io_tool.commands.wait_high(self._config.IOTool.CAMERA_PINS['Arm']))
        steps.append(self._io_tool.commands.set_high(self._config.IOTool.CAMERA_PINS['Trigger']))
        steps.append(self._io_tool.commands.set_low(self._config.IOTool.CAMERA_PINS['Trigger']))

        self._io_tool.store_program(*steps)
        self._compiled = True

    def run(self):
        """Run the assembled acquisition steps and return the images obtained."""
        if not self._compiled:
            self._compile()
        self._spectra_x.lamp_intensities(**self._spectra_x_intensities)
        self._camera.start_image_sequence_acquisition(self._num_acquisitions, trigger_mode='External Exposure',
            overlap_enabled=True, auxiliary_out_source='FireAll', pixel_readout_rate=self._readout_rate)
        self._io_tool.start_program()
        names = [self._camera.next_image(read_timeout_ms=exposure+1000) for exposure in self._exposures]
        self._io_tool.wait_for_program_done()
        self._camera.end_image_sequence_acquisition()
        return names