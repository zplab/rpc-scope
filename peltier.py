import threading
import time

from . import messaging
from .simple_rpc import property_utils
from . import scope_configuration as config

class Peltier(property_utils.PropertyDevice):
    def __init__(self, property_server=None, property_prefix=''):
        super().__init__(property_server, property_prefix)
        self._serial_port = messaging.smart_serial.Serial(config.Peltier.SERIAL_PORT, baudrate=config.Peltier.SERIAL_BAUD, timeout=4)
        # test if we can connect
        self.get_temperature()
        if property_server:
            self._update_property('temperature', self.get_temperature())
            self._update_property('target_temperature', self.get_target_temperature())
            self._sleep_time = 10
            self._timer_running = True
            self._timer_thread = threading.Thread(target=self._timer_update_temp, daemon=True)
            self._timer_thread.start()
            
    def _timer_update_temp(self):
        while self._timer_running:
            self._update_property(self.get_temperature())
            time.sleep(self._sleep_time)
           
    def _read(self):
        return self._serial_port.read_until(b'\r')[:-1].decode('ascii')

    def _write(self, val):
        self._serial_port.write(val.encode('ascii') + b'\r')

    def _call_response(self, val):
        self._write(val)
        return self._read()

    def _call_param(self, val, param):
        self._write(val + param)
        if not self._read().endswith('OK'):
            raise RuntimeError('Invalid command to incubator.')

    def get_temperature(self):
        return float(self._call_response('a'))

    def get_timer(self):
        """return (hours, minutes, seconds) tuple"""
        timer = self._call_response('b')
        return int(timer[:2]), int(timer[2:4]), int(timer[4:])
    
    def get_auto_off_mode(self):
        """return true if auto-off mode is on"""
        return self._call_response('c').endswith('On')

    def get_target_temperature(self):
        """return target temp as a float or None if no target is set."""
        temp = self._call_response('d')
        if temp == 'no target set':
            return None
        return float(temp)

    def set_target_temperature(self, temp):
        self._call_param('A', '{:.1f}'.format(temp))
        self._update_property('target_temperature', temp)

    def set_timer(self, hours, minutes, seconds):
        assert hours <= 99 and minutes <= 99 and seconds <= 99
        self._call_param('B', '{:02d}{:02d}{:02d}'.format(hours, minutes, seconds))

    def set_auto_off_mode(self, mode):
        mode_str = "ON" if mode else "OFF"
        self._call_param('C', mode_str)

    def show_temperature_on_screen(self):
        self._call_param('D')

    def show_timer_on_screen(self):
        self._call_param('E')