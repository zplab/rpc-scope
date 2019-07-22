# This code is licensed under the MIT License (see LICENSE file for details)

import threading
import time

from ..util import smart_serial
from ..util import property_device
from ..util import state_stack
from ..util import timer
from ..config import scope_configuration
from . import iotool

class Lamp(state_stack.StateStackDevice):
    def __init__(self, name, spectra):
        super().__init__()
        self._name = name
        self._spectra = spectra

    def set_intensity(self, value):
        """Set lamp intensity in the range [0, 255]"""
        self._spectra._set_intensity(self._name, value)

    def get_intensity(self):
        return self._spectra._get_intensity(self._name)

    def set_enabled(self, enabled):
        self._spectra._set_enabled(self._name, enabled)

    def get_enabled(self):
        return self._spectra._get_enabled(self._name)

class _BaseSpectra(property_device.PropertyDevice):
    _EXPECTED_INIT_ERRORS = (smart_serial.SerialException,)

    def __init__(self, iotool: iotool.IOTool, property_server=None, property_prefix=''):
        super().__init__(property_server, property_prefix)
        self._spconfig = scope_configuration.get_config().spectra
        self._serial_port = smart_serial.Serial(self._spconfig.SERIAL_PORT, timeout=1, **self._spconfig.SERIAL_ARGS)
        self._serial_port_lock = threading.RLock()
        try:
            self._initialize_spectra()
        except smart_serial.SerialTimeout:
            # explicitly clobber traceback from SerialTimeout exception
            raise smart_serial.SerialException('Could not read data from Spectra -- is it turned on?')
        self._iotool = iotool
        if property_server:
            self._timer_thread = timer.Timer(self._update_properties, interval=10)

        self._available_lamps = set(self._spconfig.IOTOOL_LAMP_PINS.keys())
        for name in self._available_lamps:
            setattr(self, name, Lamp(name, self))

        self.lamps(**{lamp+'_enabled': False for lamp in self._available_lamps})
        self.lamps(**{lamp+'_intensity': 255 for lamp in self._available_lamps})

    def _update_properties(self):
        self.get_temperature()

    def get_temperature(self):
        temp = self._get_temperature()
        self._update_property('temperature', temp)
        return temp

    def _initialize_spectra(self):
        raise NotImplementedError()

    def _set_intensity(self, lamp, value):
        raise NotImplementedError()

    def _get_temperature(self):
        raise NotImplementedError()

    def _get_intensity(self, lamp):
        raise NotImplementedError()

    def _get_enabled(self, lamp):
        raise NotImplementedError()

    def _set_enabled(self, lamp, enabled):
        self._iotool.execute(*self._iotool_lamp_commands(**{lamp: enabled}))
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
        return {lamp: self._LAMP_SPECS[lamp] for lamp in self._available_lamps}

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


def _make_dac_bytes(IIC_Addr, bit):
    dac_bytes = bytearray(b'\x53\x00\x03\x00\x00\x00\x50')
    dac_bytes[1] = IIC_Addr
    dac_bytes[3] = 1 << bit
    return dac_bytes

class SpectraX(_BaseSpectra):
    _DESCRIPTION = 'Lumencor Spectra X'
    _LAMP_DAC_COMMANDS = {
        'uv': _make_dac_bytes(0x18, 0),
        'blue': _make_dac_bytes(0x1A, 0),
        'cyan': _make_dac_bytes(0x18, 1),
        'teal': _make_dac_bytes(0x1A, 1),
        'green_yellow': _make_dac_bytes(0x18, 2),
        'red': _make_dac_bytes(0x18, 3)
    }
    _LAMP_SPECS = {
        'uv': (396, 16),
        'blue': (434, 22),
        'cyan': (481, 22),
        'teal': (508, 29),
        'green_yellow': (545, 70),
        'red': (633, 19)
    }

    def _initialize_spectra(self):
        # RS232 Lumencor docs state: "The [following] two commands MUST be issued after every power cycle to properly configure controls for further commands."
        # "Set GPIO0-3 as open drain output"
        self._serial_port.write(b'\x57\x02\xFF\x50')
        # "Set GPI05-7 push-pull out, GPIO4 open drain out"
        self._serial_port.write(b'\x57\x03\xAB\x50')
        # test if we can connect:
        self.get_temperature()
        self._lamp_intensities = {}
        self._lamp_enableds = {}

    def _get_intensity(self, lamp):
        return self._lamp_intensities[lamp]

    def _set_intensity(self, lamp, value):
        assert 0 <= value <= 255
        inverted = 255 - value
        # Put the intensity value, which is from 0xFF (off) to 0 (on), into the middle 8 bits of a 16-bit integer,
        # with the high 4 bits as 0xF and the low 4 as 0. Bizarre, but that's the wire protocol.
        intensity_bytes = 0xF000 | (inverted << 4)
        dac_bytes = self._LAMP_DAC_COMMANDS[lamp]
        dac_bytes[4] = intensity_bytes >> 8
        dac_bytes[5] = intensity_bytes & 0x00FF
        with self._serial_port_lock:
            self._serial_port.write(bytes(dac_bytes))
        self._lamp_intensities[lamp] = value
        self._update_property(lamp+'.intensity', value)

    def _get_enabled(self, lamp):
        return self._lamp_enableds[lamp]

    def _set_enabled(self, lamp, enabled):
        self._lamp_enableds[lamp] = enabled
        super()._set_enabled(lamp, enabled)

    def _get_temperature(self):
        with self._serial_port_lock:
            self._serial_port.write(b'\x53\x91\x02\x50')
            r = self._serial_port.read(2)
        return ((r[0] << 3) | (r[1] >> 5)) * 0.125


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


class SpectraError(Exception):
    pass

class SpectraIII(_BaseSpectra):
    _DESCRIPTION = 'Lumencor Spectra III'
    _LAMP_NAMES = ['uv', 'blue', 'cyan', 'teal', 'green', 'yellow', 'red', 'nIR']
    _LAMP_IDX = {lamp: i for i, lamp in enumerate(_LAMP_NAMES)}
    _LAMP_SPECS = {
        'uv': (390, 22),
        'blue': (440, 20),
        'cyan': (475, 28),
        'teal': (510, 25),
        'green': (555, 28),
        'yellow': (575, 25),
        'red': (635, 22),
        'nIR': (747.5, 11)
    }
    _ERROR_CODES = {
        '41': 'Invalid I2C bus',
        '42': 'Invalid I2C slave (device) address',
        '43': 'I2C bus write error',
        '44': 'I2C bus read error',
        '45': 'SPI bus write error',
        '46': 'SPI bus read error',
        '47': 'GPIO set state error',
        '48': 'GPIO get state error',
        '49': 'Analog input sampling error',
        '51': 'Invalid light channel index',
        '52': 'Invalid command format (syntax)',
        '53': 'Unknown command',
        '55': 'Invalid command argument (invalid argument value or type)',
        '56': 'Hardware component unavailable / Hardware configuration error',
        '57': 'Channel locked, because one of the following occurred: Fan malfunction, Max temperature was exceeded, Interlock activated, Power supply current limit exceeded',
        '58': 'System is busy (long running operation)',
        '59': 'Set intensity command failed because one of the channels is under PID control',
        '60': 'Interlock active',
        '61': 'Feature unavailable',
        '62': 'Governor lock acquired (permanent)',
        '63': 'Governor prediction lock acquired',
        '64': 'TEC lock active',
        '65': 'TEC temperature out of range (temperature control error)',
        '66': 'Permanent storage error (eMMC)',
        '67': 'Invalid system configuration',
        '68': 'Invalid app configuration',
        '69': 'Invalid serial interface configuration (both ports in legacy mode)',
        '70': 'Unauthorized access',
        '71': 'Power level exceeds the power limt (power reference clipped)',
        '72': 'Power regulation unavailable for multiple channels on the same power sensor'
    }
    _STATUS_CODES = {
        '0': 'OK',
        '1': 'Fan malfunction',
        '2': 'High temperature (over 25 C)',
        '3': 'High temperature and fan malfunction',
        '4': 'Device safety lock active',
        '5': 'Invalid hardware configuration'
    }
    _LAMP_STATUS_CODES = {
        '0': 'OK',
        '51': 'Invalid channel index',
        '56': 'Invalid hardware configuration',
        '57': 'Channel locked, because one of the following occurred: Fan malfunction, Max temperature was exceeded, Interlock activated, Power supply current limit exceeded',
        '58': 'Channel busy (long running operation)',
        '60': 'Interlock active',
        '64': 'TEC lock active',
        '65': 'TEC temperature out of range (temperature control error)'
    }

    def send_command(self, cmd):
        cmdname = cmd.split(' ')[1]
        with self._serial_port_lock:
            self._serial_port.write(cmd.encode('ascii') + b'\r')
            code, name_out, *ret = self._serial_port.read_until(b'\r\n')[:-2].decode('ascii').split(' ')
        if len(ret) == 1:
            ret = ret[0]
        elif len(ret) == 0:
            ret = None
        if code != 'A':
            raise SpectraError(f'Error from Spectra III: command "{cmd}" returned error "{self._ERROR_CODES[ret]}"')
        if name_out != cmdname:
            raise SpectraError(f'Unknown response to command "{cmd}": "{cmd_out}"')
        return ret

    def _initialize_spectra(self):
        self.send_command('SET TTLENABLE 1')
        self.send_command('SET TTLPOL 1')
        status = self.get_status()
        if status != 'OK':
            raise SpectraError(f'Spectra III in error condition: "{status}"')
        errs = []
        for lamp, status in self.get_lamps_status().items():
            if status != 'OK':
                errs.append(f'{lamp}: {status}')
        if len(errs) != 0:
            raise SpectraError('Lamps not ready:\n' + '\n'.join(errs))

    def get_status(self):
        return self._STATUS_CODES[self.send_command('GET STAT')]

    def get_lamps_status(self):
        values = self.send_command('GET MULCHSTAT')
        return {lamp: self._LAMP_STATUS_CODES[value] for lamp, value in zip(self._LAMP_NAMES, values)}

    def get_intensities(self):
        values = self.send_command('GET MULCHINT')
        intensities = {lamp: int(round(int(value) * 255/1000)) for lamp, value in zip(self._LAMP_NAMES, values)}
        for lamp, value in intensities.items():
            self._update_property(lamp+'.intensity', value)
        return intensities

    def _get_intensity(self, lamp):
        return self.get_intensities()[lamp]

    def _set_intensity(self, lamp, value):
        assert 0 <= value <= 255
        # Spectra III has 1000 intensity values, but 255 is enough for us...
        self.send_command(f'SET CHINT {self._LAMP_IDX[lamp]} {int(round(value * 1000/255))}')
        self._update_property(lamp+'.intensity', value)

    def get_lamps_enabled(self):
        values = self.send_command('GET MULCHACT')
        enableds = {lamp: bool(int(value)) for lamp, value in zip(self._LAMP_NAMES, values)}
        for lamp, value in enableds.items():
            self._update_property(lamp+'.enabled', value)
        return enableds

    def _get_enabled(self, lamp):
        return self.get_lamps_enabled()[lamp]

    def _get_temperature(self):
        return float(self.send_command('GET TEMP'))

    def get_power_usage(self):
        return float(self.send_command('GET SUPPLYPOWER'))

    def _update_properties(self):
        super()._update_properties()
        self.get_power_usage()
        self.get_intensities()
        self.get_lamps_enabled()
