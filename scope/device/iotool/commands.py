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

from ...config import scope_configuration

class Commands:
    def __init__(self):
        self._config = scope_configuration.get_config()

    def _make_command(self, *elements):
        return ' '.join(map(str, elements))

    def wait_high(self, pin):
        return self._make_command('wh', pin)

    def wait_low(self, pin):
        return self._make_command('wl', pin)

    def wait_change(self, pin):
        return self._make_command('wc', pin)

    def wait_time(self, time):
        return self._make_command('wt', time)

    def read_digital(self, pin):
        return self._make_command('rd', pin)

    def read_analog(self, pin):
        return self._make_command('ra', pin)

    def delay_ms(self, delay):
        return self._make_command('dm', delay)

    def delay_us(self, delay):
        return self._make_command('du', delay)

    def timer_begin(self):
        return self._make_command('tb')

    def timer_end(self):
        return self._make_command('te')

    def pwm(self, pin, value):
        return self._make_command('pm', pin, value)

    def set_high(self, pin):
        return self._make_command('sh', pin)

    def set_low(self, pin):
        return self._make_command('sl', pin)

    def set_tristate(self, pin):
        return self._make_command('st', pin)

    def char_transmit(self, byte):
        return self._make_command('ct', byte)

    def char_receive(self):
        return self._make_command('cr')

    def loop(self, index, count):
        return self._make_command('lo', index, count)

    def goto(self, index):
        return self._make_command('go', index)

    def spectra_lamps(self, **lamps):
        """Produce a sequence of IOTool commands to enable and disable given
        Spectra X lamps.

        Keyword arguments must be lamp names, as specified in
        scope_configuration.LUMENCOR_PINS. The values specified must be True to
        enable that lamp, False to disable, or None to do nothing (unspecified
        lamps are also not altered)."""
        commands = []
        for lamp, enabled in lamps.items():
            if enabled is None:
                continue
            pin = self._config.IOTool.LUMENCOR_PINS[lamp]
            if enabled:
                commands.append(self.set_high(pin))
            else:
                commands.append(self.set_low(pin))
        return commands

    def transmitted_lamp(self, enabled=None, intensity=None):
        """Produce a sequence of IOTool commands to enable/disable and control the
        intensity of the TL lamp.

        Parameters
            enabled: True (lamp on), False (lamp off), or None (no change).
            intensity: None (no change) or value in the range [0, 255].
        """
        commands = []
        if intensity is not None:
            assert 0 <= intensity <= self._config.IOTool.TL_PWM_MAX
            commands.append(self.pwm(self._config.IOTool.TL_PWM_PIN, intensity))
        if enabled is not None:
            if enabled:
                commands.append(self.set_high(self._config.IOTool.TL_ENABLE_PIN))
            else:
                commands.append(self.set_low(self._config.IOTool.TL_ENABLE_PIN))
        return commands