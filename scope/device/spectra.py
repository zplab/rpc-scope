
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
from . import iotool

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
    def __init__(self, name, spectra):
        super().__init__()
        self._name = name
        self._spectra = spectra

    def set_intensity(self, value):
        """Set lamp intensity in the range [0, 255]"""
        self._spectra._lamp_intensity(self._name, value)

    def get_intensity(self):
        return self._spectra._lamp_intensities[self._name]

    def set_enabled(self, enabled):
        self._spectra._lamp_enable(self._name, enabled)

    def get_enabled(self):
        return self._spectra._lamp_enableds[self._name]

class SpectraX(property_device.PropertyDevice):
    _DESCRIPTION = 'Lumencor Spectra X'
    _EXPECTED_INIT_ERRORS = (smart_serial.SerialException,)

    def __init__(self, iotool: iotool.IOTool, property_server=None, property_prefix=''):
        super().__init__(property_server, property_prefix)
        self._spconfig = scope_configuration.get_config().spectra
        self._serial_port = smart_serial.Serial(self._spconfig.SERIAL_PORT, timeout=1, **self._spconfig.SERIAL_ARGS)
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
            raise smart_serial.SerialException('Could not read data from Spectra -- is it turned on?')
        self._iotool = iotool
        if property_server:
            self._update_property('temperature', self.get_temperature())
            self._sleep_time = 10
            self._timer_running = True
            self._timer_thread = threading.Thread(target=self._timer_update_temp, daemon=True)
            self._timer_thread.start()

        self._available_lamps = set(self._spconfig.IOTOOL_LAMP_PINS.keys())
        for name in self._available_lamps:
            setattr(self, name, Lamp(name, self))

        self._lamp_intensities = {}
        self._lamp_enableds = {}
        self.lamps(**{lamp+'_enabled':False for lamp in self._available_lamps})
        self.lamps(**{lamp+'_intensity':255 for lamp in self._available_lamps})

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

    def _lamp_enable(self, lamp, enabled):
        self._iotool.execute(*self._iotool_lamp_commands(**{lamp:enabled}))
        self._lamp_enableds[lamp] = enabled
        self._update_property(lamp+'.enabled', enabled)

    def _iotool_lamp_commands(self, **lamps):
        """Produce a sequence of IOTool commands to enable and disable given
        Spectra lamps.

        Keyword arguments must be lamp names, as specified in the scope configuration.
        The values specified must be True to enable that lamp, False to disable,
        or None to do nothing (unspecified lamps are also not altered)."""
        commands = []
        for lamp, enabled in lamps.items():
            if enabled is None:
                continue
            pin = self._spconfig.IOTOOL_LAMP_PINS[lamp]
            if enabled:
                commands.append(self._iotool.commands.set_high(pin))
            else:
                commands.append(self._iotool.commands.set_low(pin))
        return commands

    def get_lamp_specs(self):
        """Return a dict mapping lamp names to tuples of (peak_wavelength, bandwidth), in nm,
        where bandwidth is the minimum width required to contain 75% of the spectral intensity
        of the lamp output."""
        return {lamp:LAMP_SPECS[lamp] for lamp in self._available_lamps}

    def get_temperature(self):
        self._serial_port.write(b'\x53\x91\x02\x50')
        r = self._serial_port.read(2)
        return ((r[0] << 3) | (r[1] >> 5)) * 0.125

    def lamps(self, **lamp_parameters):
        """Set a number of lamp parameters at once using keyword arguments, e.g.
        spectra.lamps(red_enabled=True, red_intensity=255, blue_enabled=False)

        Intensity values must be in the range [0, 255]. Valid lamp names can be
        retrieved with get_lamp_specs().
        """
        self._set_state(lamp_parameters.items())

    def _get_getter_setter(self, prop):
        """Return a property setter/getter pair, either from a "real" property
        get/set pair, or a "virtual" property like "red_enabled" or "cyan_intensity"."""
        if hasattr(self, 'set_'+prop):
            return getattr(self, 'get_'+prop), getattr(self, 'set_'+prop)
        else:
            lamp_name, lamp_prop = prop.rsplit('_', 1)
            if lamp_name not in self._available_lamps:
                raise ValueError('Invalid lamp name')
            lamp = getattr(self, lamp_name)
            if hasattr(lamp, 'set_'+ lamp_prop):
                return getattr(lamp, 'get_'+lamp_prop), getattr(lamp, 'set_'+lamp_prop)
            else:
                raise ValueError('Invalid lamp parameter "{}"'.format(lamp_prop))

    def _set_state(self, properties_and_values):
        for prop, value in properties_and_values:
            setter = self._get_getter_setter(prop)[1]
            setter(value)

    def push_state(self, **lamp_parameters):
        """Set a number of parameters at once using keyword arguments, while
        saving the old values of those parameters. (See lamps() for a description
        of valid parameters.) pop_state() will restore those previous values.
        push_state/pop_state pairs can be nested arbitrarily."""
        # Also note that we do not filter out identical states from being pushed.
        # Since the enabled state can be fiddled with IOTool, there is good reason
        # for pushing an enabled state identical to the current one, so that it
        # will be restored after any such fiddling.
        old_state = {}
        for prop, value in lamp_parameters.items():
            getter, setter = self._get_getter_setter(prop)
            old_state[prop] = getter()
            setter(value)
        self._state_stack.append(old_state)

class Spectra(SpectraX):
    _DESCRIPTION = 'Lumencor Spectra'

    def __init__(self, iotool: iotool.IOTool, property_server=None, property_prefix=''):
        super().__init__(iotool, property_server, property_prefix)
        self.set_green_yellow_filter('green')

    def _iotool_enable_green_command(self):
        """Produce a command that switches the green/yellow paddle to the green filter position."""
        return self._iotool.commands.set_high(self._spconfig.IOTOOL_GREEN_YELLOW_SWITCH_PIN)

    def _iotool_enable_yellow_command(self):
        """Produce a command that switches the green/yellow paddle to the yellow filter position."""
        return self._iotool.commands.set_low(self._spconfig.IOTOOL_GREEN_YELLOW_SWITCH_PIN)

    def set_green_yellow_filter(self, position):
        """'position' should be either 'green' or 'yellow' to insert the
        corresponding excitation filter into the green/yellow beam."""
        if position not in {'green', 'yellow'}:
            raise ValueError('"position" parameter must be either "green" or "yellow"')
        if position == 'green':
            self._iotool.execute(self._iotool_enable_green_command())
        else:
            self._iotool.execute(self._iotool_enable_yellow_command())
        time.sleep(self._spconfig.FILTER_SWITCH_DELAY)
        self._green_yellow_pos = position
        self._update_property('green_yellow_filter', position)

    def get_green_yellow_filter(self):
        return self._green_yellow_pos
