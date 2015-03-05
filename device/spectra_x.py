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
from ..config import scope_configuration

def _make_dac_bytes(IIC_Addr, bit):
    dac_bytes = bytearray(b'\x53\x00\x03\x00\x00\x00\x50')
    dac_bytes[1] = IIC_Addr
    dac_bytes[3] = 1<<bit
    return dac_bytes

LAMP_DAC_COMMANDS = {
    'UV': _make_dac_bytes(0x18, 0),
    'Blue': _make_dac_bytes(0x1A, 0),
    'Cyan': _make_dac_bytes(0x18, 1),
    'Teal': _make_dac_bytes(0x1A, 1),
    'GreenYellow': _make_dac_bytes(0x18, 2),
    'Red': _make_dac_bytes(0x18, 3)
}

LAMP_SPECS = {
    'UV': (396, 16),
    'Blue': (434, 22),
    'Cyan': (481, 22),
    'Teal': (508, 29),
    'GreenYellow': (545, 70),
    'Red': (633, 19)
}

LAMP_NAMES = set(LAMP_DAC_COMMANDS.keys())

class Lamp:
    def __init__(self, name, spectra_x):
        self._name = name
        self._spectra_x = spectra_x

    def set_intensity(self, value):
        self._spectra_x.lamp_intensities(**{self._name:value})

    def get_intensity(self):
        return self._spectra_x._lamp_intensities[self._name]

    def set_enabled(self, enable):
        self._spectra_x.lamp_enableds(**{self._name:enable})

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
        self.lamp_enableds(**{lamp:False for lamp in LAMP_NAMES})
        self.lamp_intensities(**{lamp:255 for lamp in LAMP_NAMES})
        for name in LAMP_NAMES:
            setattr(self, name, Lamp(name, self))
        self._state_stack = []

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

    def lamp_intensities(self, **lamps):
        """Set intensity of named lamps to a given value.

        The keyword argument names must be valid lamp names. The values must be
        in the range [0, 255], or None to do nothing. (Lamps not specified as
        arguments are also not altered)."""
        for lamp, value in lamps.items():
            if value is not None:
                self._lamp_intensity(lamp, value)

    def lamp_enableds(self, **lamps):
        """Turn off or on named lamps.

        The keyword argument names must be valid lamp names. The values must be
        either True to enable that lamp, False to disable, or None to do nothing.
        (Lamps not specified as arguments are also not altered)."""
        self._iotool.execute(*self._iotool.commands.spectra_x_lamps(**lamps))
        for lamp, enable in lamps.items():
            if enable is not None:
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

    def set_state(self, **state):
        """Set a number of parameters at once using keyword arguments, e.g.
        spectra_x.set_state(Red_enabled=True, Red_intensity=255, Blue_enabled=False)"""
        lamp_intensities = {}
        lamp_enableds = {}
        prop_args = {
            'intensity':lamp_intensities,
            'enabled':lamp_enableds}
        for lamp_prop, value in state.items():
            lamp, prop = lamp_prop.split('_')
            prop_args[prop][lamp] = value
        self.lamp_enableds(**lamp_enableds)
        self.lamp_intensities(**lamp_intensities)

    def push_state(self, **state):
        """Set a number of parameters at once using keyword arguments, while
        saving the old values of those parameters. pop_state() will restore those
        previous values. push_state/pop_state pairs can be nested arbitrarily."""
        prop_stores = {
            'intensity':self._lamp_intensities,
            'enabled':self._lamp_enableds}
        old_state = {}
        for lamp_prop in state.keys():
            lamp, prop = lamp_prop.split('_')
            old_state[lamp_prop] = prop_stores[prop][lamp]
        self._state_stack.append(old_state)
        self.set_state(**state)

    def pop_state(self):
        """Restore the most recent set of camera parameters changed by a push_state()
        call."""
        self.set_state(**self._state_stack.pop())
