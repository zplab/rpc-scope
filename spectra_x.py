import threading
import time

from .messaging import smart_serial
from .simple_rpc import property_utils
from . import scope_configuration as config

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

class SpectraX(property_utils.PropertyDevice):
    def __init__(self, iotool, property_server=None, property_prefix=''):
        super().__init__(property_server, property_prefix)
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

        self.lamp_enable(**{lamp:False for lamp in LAMP_NAMES})
        self.lamp_intensity(**{lamp:255 for lamp in LAMP_NAMES})

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
        self._update_property(lamp+'.intensity', value)

    def lamp_intensity(self, **lamps):
        """Set intensity of named lamp to a given value.

        The keyword argument names must be valid lamp names. The values must be
        in the range [0, 255], or None to do nothing. (Lamps not specified as
        arguments are also not altered)."""
        for lamp, value in lamps.items():
            if value is not None:
                self._lamp_intensity(lamp, value)

    def lamp_enable(self, **lamps):
        """Turn off or on named lamps.

        The keyword argument names must be valid lamp names. The values must be
        either True to enable that lamp, False to disable, or None to do nothing.
        (Lamps not specified as arguments are also not altered)."""
        self._iotool.execute(*self._iotool.commands.spectra_x_lamps(**lamps))
        for lamp, enable in lamps.items():
            if enable is not None:
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
