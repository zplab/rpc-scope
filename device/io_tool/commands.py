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

from .. import scope_configuration as _config

def _make_command(*elements):
    return ' '.join(map(str, elements))

def wait_high(pin):
    return _make_command('wh', pin)

def wait_low(pin):
    return _make_command('wl', pin)

def wait_change(pin):
    return _make_command('wc', pin)

def wait_time(time):
    return _make_command('wt', time)

def read_digital(pin):
    return _make_command('rd', pin)

def read_analog(pin):
    return _make_command('ra', pin)

def delay_ms(delay):
    return _make_command('dm', delay)

def delay_us(delay):
    return _make_command('du', delay)

def timer_begin():
    return _make_command('tb')

def timer_end():
    return _make_command('te')

def pwm(pin, value):
    return _make_command('pm', pin, value)

def set_high(pin):
    return _make_command('sh', pin)

def set_low(pin):
    return _make_command('sl', pin)

def set_tristate(pin):
    return _make_command('st', pin)

def char_transmit(byte):
    return _make_command('ct', byte)

def char_receive(cls):
    return _make_command('cr')

def loop(index, count):
    return _make_command('lo', index, count)

def goto(index):
    return _make_command('go', index)

def spectra_x_lamps(**lamps):
    """Produce a sequence of IOTool commands to enable and disable given
    Spectra X lamps.

    Keyword arguments must be lamp names, as specified in
    scope_configuration.LUMENCOR_PINS. The values specified must be True to
    enable that lamp, False to disable, or None to do nothing (unspecified
    lamps are also not altered)."""
    commands = []
    for lamp, enable in lamps.items():
        if enable is None:
            continue
        pin = _config.IOTool.LUMENCOR_PINS[lamp]
        if enable:
            commands.append(set_high(pin))
        else:
            commands.append(set_low(pin))
    return commands

def transmitted_lamp(enable=None, intensity=None):
    """Produce a sequence of IOTool commands to enable/disable and control the
    intensity of the TL lamp.

    Parameters
    enable: True (lamp on), False (lamp off), or None (no change).
    intensity: None (no change) or value in the range [0, 255] for min to max.
    """
    commands = []
    if intensity is not None:
        assert 0 <= intensity <= _config.IOTool.TL_PWM_MAX
        commands.append(pwm(_config.IOTool.TL_PWM_PIN, intensity))
    if enable is not None:
        if enable:
            commands.append(set_high(_config.IOTool.TL_ENABLE_PIN))
        else:
            commands.append(set_low(_config.IOTool.TL_ENABLE_PIN))
    return commands