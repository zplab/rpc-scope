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

class TemperatureController(property_device.PropertyDevice):
    _DESCRIPTION = 'temperature controller'
    _EXPECTED_INIT_ERRORS = (smart_serial.SerialException,)

    def __init__(self, serial_config, property_server=None, property_prefix=''):
        super().__init__(property_server, property_prefix)
        self._serial_port = smart_serial.Serial(serial_config.SERIAL_PORT, timeout=1, **serial_config.SERIAL_ARGS)
        self._serial_port.clear_input_buffer() # bad configurations can leave garbage in the Anova input buffer
        try:
            self.get_temperature()
        except smart_serial.SerialTimeout:
            # explicitly clobber traceback from SerialTimeout exception
            raise smart_serial.SerialException('Could not read data from temperature controller -- is it turned on?')
        if property_server:
            self._update_property('temperature', self.get_temperature())
            self._update_property('target_temperature', self.get_target_temperature())
            self._sleep_time = 10
            self._timer_running = True
            self._timer_thread = threading.Thread(target=self._timer_update_temp, daemon=True)
            self._timer_thread.start()

    def _read(self):
        return self._serial_port.read_until(b'\r')[:-1].decode('ascii')

    def _write(self, val):
        self._serial_port.write(val.encode('ascii') + b'\r')

    def _timer_update_temp(self):
        while self._timer_running:
            self._update_property('temperature', self.get_temperature())
            time.sleep(self._sleep_time)

    def get_temperature(self):
        temp = self._get_temperature()
        self._update_property('temperature', temp)
        return temp

    def set_target_temperature(self, temp):
        temp_out = self._set_target_temperature(temp)
        self._update_property('target_temperature', temp_out)


class Peltier(TemperatureController):
    _DESCRIPTION = 'Peltier controller'

    def __init__(self, property_server=None, property_prefix=''):
        serial_config = scope_configuration.get_config().peltier
        super().__init__(serial_config, property_server, property_prefix)

    def _call_response(self, val):
        self._write(val)
        return self._read()

    def _call(self, val, param=''):
        if param:
            val = val + ' ' + param
        self._write(val)
        if not self._read().endswith('OK'):
            raise ValueError('Invalid command to incubator.')

    def _get_temperature(self):
        return float(self._call_response('a'))

    def get_target_temperature(self):
        """return target temp as a float or None if no target is set."""
        temp = self._call_response('d')
        if temp == 'no target set':
            return None
        return float(temp)

    def _set_target_temperature(self, temp):
        self._call('A', '{:.1f}'.format(temp))
        return round(temp, 1)

    def set_timer(self, hours, minutes, seconds):
        assert hours <= 99 and minutes <= 99 and seconds <= 99
        self._call('B', '{:02d}{:02d}{:02d}'.format(hours, minutes, seconds))

    def set_auto_off_mode(self, mode):
        mode_str = "ON" if mode else "OFF"
        self._call('C', mode_str)

    def show_temperature_on_screen(self):
        self._call('D')

    def show_timer_on_screen(self):
        self._call('E')

class Circulator(TemperatureController):
    _DESCRIPTION = 'Anova circulator'

    def __init__(self, property_server=None, property_prefix=''):
        serial_config = scope_configuration.get_config().circulator
        super().__init__(serial_config, property_server, property_prefix)

    def _call_response(self, val):
        self._write(val)
        echo = self._read()
        if echo != val: # read back echo
            raise RuntimeError('unexpected serial response: "{}"'.format(echo))
        return self._read()

    def _get_temperature(self):
        return float(self._call_response('temp'))

    def get_target_temperature(self):
        temp = self._call_response('get temp setting')
        return float(temp)

    def _set_target_temperature(self, temp):
        ret = self._call_response('set temp {:.2f}'.format(temp))
        if ret.startswith('Error'):
            self._read() # clear a stray \n\r from the output
            raise ValueError('invalid temperature setting')
        return float(ret)