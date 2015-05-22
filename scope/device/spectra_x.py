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

import threading
import time

from ..util import smart_serial
from ..util import property_device
from ..util import state_stack
from ..config import scope_configuration

def _make_dac_bytes(IIC_Addr, bit):
    dac_bytes = bytearray(b'\x53\x00\x03\x00\x00\x00\x50')
    dac_bytes[1] = IIC_Addr
    dac_bytes[3] = 1<<bit
    return dac_bytes

LAMP_DAC_COMMANDS = {
    'uv': _make_dac_bytes(0x18, 0),
    'blue': _make_dac_bytes(0x1A, 0),
    'cyan': _make_dac_bytes(0x18, 1),
    'teal': _make_dac_bytes(0x1A, 1),
    'green_yellow': _make_dac_bytes(0x18, 2),
    'red': _make_dac_bytes(0x18, 3)
}

LAMP_SPECS = {
    'uv': (396, 16),
    'blue': (434, 22),
    'cyan': (481, 22),
    'teal': (508, 29),
    'green_yellow': (545, 70),
    'red': (633, 19)
}

LAMP_NAMES = set(LAMP_DAC_COMMANDS.keys())

class Lamp(state_stack.StateStackDevice):
    def __init__(self, name, spectra_x):
        super().__init__()
        self._name = name
        self._spectra_x = spectra_x

    def set_intensity(self, value):
        """Set lamp intensity in the range [0, 255]"""
        self._spectra_x._lamp_intensity(self._name, value)

    def get_intensity(self):
        return self._spectra_x._lamp_intensities[self._name]

    def set_enabled(self, enable):
        self._spectra_x._lamp_enable(self._name, enable)

    def get_enabled(self):
        return self._spectra_x._lamp_enableds[self._name]

class SpectraX(property_device.PropertyDevice):
    def __init__(self, iotool, property_server=None, property_prefix=''):
        super().__init__(property_server, property_prefix)
        config = scope_configuration.get_config()
        self._serial_port = smart_serial.Serial(config.SpectraX.SERIAL_PORT, baudrate=config.SpectraX.SERIAL_BAUD, timeout=1)
        # RS232 Lumencor docs state: "The [following] two commands MUST be issued after every power cycle to properly configure controls for further commands."
        # "Set GPIO0-3 as open drain output"
        self._serial_port.write(b'\x57\x02\xFF\x50')
        # "Set GPI05-7 push-pull out, GPIO4 open drain out"
        self._serial_port.write(b'\x57\x03\xAB\x50')
        # test if we can connect:
        try:
            self.get_temperature()
        except smart_serial.SerialTimeout:
            # explicitly clobber traceback from SerialTimeout exception
            raise smart_serial.SerialException('Could not read data from Spectra X -- is it turned on?')
        self._iotool = iotool
        if property_server:
            self._update_property('temperature', self.get_temperature())
            self._sleep_time = 10
            self._timer_running = True
            self._timer_thread = threading.Thread(target=self._timer_update_temp, daemon=True)
            self._timer_thread.start()

        self._lamp_intensities = {}
        self._lamp_enableds = {}
        self.lamps(**{lamp+'_enabled':False for lamp in LAMP_NAMES})
        self.lamps(**{lamp+'_intensity':255 for lamp in LAMP_NAMES})
        for name in LAMP_NAMES:
            setattr(self, name, Lamp(name, self))

    def _timer_update_temp(self):
        while self._timer_running:
            self._update_property('temperature', self.get_temperature())
            time.sleep(self._sleep_time)

    def _lamp_intensity(self, lamp, value):
        assert 0 <= value <= 255
        inverted = 255 - value
        # Put the intensity value, which is from 0xFF (off) to 0 (on), into the middle 8 bits of a 16-bit integer,
        # with the high 4 bits as 0xF and the low 4 as 0. Bizarre, but that's the wire protocol.
        intensity_bytes = 0xF000 | (inverted << 4)
        dac_bytes = LAMP_DAC_COMMANDS[lamp]
        dac_bytes[4] = intensity_bytes >> 8
        dac_bytes[5] = intensity_bytes & 0x00FF
        self._serial_port.write(bytes(dac_bytes))
        self._lamp_intensities[lamp] = value
        self._update_property(lamp+'.intensity', value)

    def _lamp_enable(self, lamp, enable):
        self._iotool.execute(*self._iotool.commands.spectra_x_lamps(**{lamp:enable}))
        self._lamp_enableds[lamp] = enable
        self._update_property(lamp+'.enabled', enable)

    def get_lamp_specs(self):
        """Return a dict mapping lamp names to tuples of (peak_wavelength, bandwidth), in nm,
        where bandwidth is the minimum width required to contain 75% of the spectral intensity
        of the lamp output."""
        return LAMP_SPECS

    def get_temperature(self):
        self._serial_port.write(b'\x53\x91\x02\x50')
        r = self._serial_port.read(2)
        return ((r[0] << 3) | (r[1] >> 5)) * 0.125

    def _set_state(self, **lamp_parameters):
        """Set a number of lamp parameters at once using keyword arguments, e.g.
        spectra_x.lamps(red_enabled=True, red_intensity=255, blue_enabled=False)

        Intensity values must be in the range [0, 255]. Valid lamp names can be
        retrieved with get_lamp_specs().
        """
        for lamp_prop, value in lamp_parameters.items():
            lamp, prop = self._get_lamp_and_prop(lamp_prop)
            if prop == 'intensity':
                self._lamp_intensity(lamp, value)
            else:
                self._lamp_enable(lamp, value)

    lamps = _set_state # provide a public interface to state-setting for Spectra X

    def _get_lamp_and_prop(self, lamp_prop):
        """Split a 'lamp_property' style string into a lamp and property value,
        validating each."""
        lamp, prop = lamp_prop.rsplit('_', 1)
        if lamp not in LAMP_SPECS:
            raise ValueError('Invalid lamp name')
        if prop not in {'intensity', 'enabled'}:
            raise ValueError('Invalid lamp parameter: must be "intensity" or "enabled"')
        return lamp, prop

    def push_state(self, **lamp_parameters):
        """Set a number of parameters at once using keyword arguments, while
        saving the old values of those parameters. (See lamps() for a description
        of valid parameters.) pop_state() will restore those previous values.
        push_state/pop_state pairs can be nested arbitrarily."""
        old_state = {}
        for lamp_prop in lamp_parameters.keys():
            lamp, prop = self._get_lamp_and_prop(lamp_prop)
            if prop == 'intensity':
                old_state[lamp_prop] = self._lamp_intensities[lamp]
            else:
                old_state[lamp_prop] = self._lamp_enableds[lamp]
        self._state_stack.append(old_state)
        self._set_state(**lamp_parameters)

