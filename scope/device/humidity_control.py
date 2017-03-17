# The MIT License (MIT)
#
# Copyright (c) 2014-2017 WUSTL ZPLAB
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
import collections
import time

from ..util import smart_serial
from ..util import property_device
from ..util import timer
from ..config import scope_configuration

COMMAND_CHAR = b'*'

def decode_hex_rh(value):
    assert len(value) == 6
    value = int(value, base=16)
    if value & (15<<20) != 2<<20: # top 4 bits must be 0010, which means format = +000.0
        raise ValueError('Bad data format.')
    value &= (1<<20) - 1 # get contents of bottom 20 bits
    value /= 10
    return value

def encode_hex_rh(value):
    if not 100 >= value >= 0:
        raise ValueError('RH value must be between 0 and 100%.')
    value = hex(int(round(value*10)) + (2<<20))[2:].upper()
    assert len(value) == 6
    return value

class HumidityController(property_device.PropertyDevice):
    _DESCRIPTION = 'humidity controller'
    _EXPECTED_INIT_ERRORS = (smart_serial.SerialException,)
    _UPDATE_INTERVAL = 10
    _RECORD_DAYS = 14

    def __init__(self, property_server=None, property_prefix=''):
        super().__init__(property_server, property_prefix)
        config = scope_configuration.get_config().humidifier
        self._serial_port = smart_serial.Serial(config.SERIAL_PORT, timeout=1, **config.SERIAL_ARGS)
        self._serial_port.clear_input_buffer()
        self._serial_port_lock = threading.RLock()
        try:
            self.reset()
        except smart_serial.SerialTimeout:
            # explicitly clobber traceback from SerialTimeout exception
            raise smart_serial.SerialException('Could not read data from humidity controller -- is it turned on?')
        self._reset_thread = timer.Timer(self.reset, interval=24*60*60, run_immediately=False) # reset controller daily

        num_data_to_log = int(self._RECORD_DAYS*24*60*60 / self._UPDATE_INTERVAL)
        self._logged_data = collections.deque(maxlen=num_data_to_log)
        self._update_thread = timer.Timer(self._update_properties, interval=self._UPDATE_INTERVAL)

    def _call(self, val):
        with self._serial_port_lock:
            self._serial_port.write(COMMAND_CHAR + val.encode('ascii') + b'\r')
            out = self._serial_port.read_until(b'\r')[:-1].decode('ascii')
        if out.startswith('?'):
            raise ValueError('Command "{}" produced error "{}".'.format(val, out))
        if not out[:3] == val[:3]:
            raise ValueError('Unexpected output of command "{}": "{}".'.format(val, out))
        return out[3:]

    def _update_properties(self):
            humidity, temperature = self.get_data()
            self.get_target_humidity()
            self._logged_data.append((time.time(), humidity, temperature))

    def full_reset(self):
        with self._serial_port_lock:
            self._call('P1F14') # store in RAM bus format: echo, no LF, no continuous xmit
            self._call('W1F14') # bus format: echo, no LF, no continuous xmit
            self._call('D01') # disable alarm 1 / enable output 1
            self._call('D02') # disable alarm 2 / enable output 2 (not used)
            self._call('W0C20') # configure output 1 as on/off only
            self._call('W2006') # data format: RH and Temp
            self._call('W1101') # alarm color amber
            self._call('W09A2') # alarm 1 output off, alarm enabled at power on, deviation high/low
            self._call('W12' + encode_hex_rh(5)) # alarm 1 low = 5% RH deviation
            self._call('W13' + encode_hex_rh(3)) # alarm 1 high = 3% RH deviation
            self._call('W170014') # RH dead-band of 2% (0014 is hex for 20 = 2%)
            self.reset()

    def reset(self):
        with self._serial_port_lock:
            self._call('Z02')
            retries = 0
            timeout = self._serial_port.timeout
            self._serial_port.timeout = 0.25
            while True:
                self._serial_port.write(COMMAND_CHAR + b'U03\r')
                try:
                    self._serial_port.read_until(b'\r')
                    break
                except smart_serial.SerialTimeout:
                    retries += 1
                    if retries > 20: # 5 seconds to timeout
                        raise RuntimeError('Could not reestablish connection to humidifier after reset.')
            self._serial_port.timeout = timeout
            self._serial_port.clear_input_buffer()
            self._call('E03') # enable run mode
            self._call('D04') # disable self-control mode

    def get_temperature(self):
        temperature = float(self._call('X02'))
        self._update_property('temperature', temperature)
        return temperature

    def get_humidity(self):
        humidity = float(self._call('X01'))
        self._update_property('humidity', humidity)
        return humidity

    def get_data(self):
        humidity, temperature = map(float, self._call('V01')[1:].split(' '))
        self._update_property('humidity', humidity)
        self._update_property('temperature', temperature)
        return humidity, temperature

    def get_logged_data(self):
        return list(self._logged_data)

    def get_target_humidity(self):
        humidity = decode_hex_rh(self._call('R01'))
        self._update_property('target_humidity', humidity)
        return humidity

    def set_target_humidity(self, humidity):
        hexval = encode_hex_rh(humidity)
        self._call('P01' + hexval) # put RH setpoint into RAM
        self._call('W01' + hexval) # write RH setpoint into EEPROM
        self._update_property('target_humidity', humidity)
