import time

from .. import messaging
from . import commands
from .. import scope_configuration as config

_ECHO_OFF = b'\x80\xFF'

class IOTool:
    def __init__(self):
        self._serial_port = messaging.smart_serial.Serial(config.IOTool.SERIAL_PORT, timeout=1)
        self._serial_port.write(b'!\nreset\n') # force the IOTool box to reset to known-good state
        time.sleep(0.5) # give it time to reboot
        self._serial_port = messaging.smart_serial.Serial(config.IOTool.SERIAL_PORT, timeout=1)
        self._serial_port.write(_ECHO_OFF + b'\n') # disable echo
        echo_reply = self._serial_port.read_until(b'>')[:-1]
        assert echo_reply == _ECHO_OFF + b'\r\n' # read back echo of above (no further echoes will come)
        self._assert_empty_buffer()
        self.commands = commands
        self._serial_port.setTimeout(None) # change to infinite time-out once initialized and in known-good state,
        # so that waiting for IOTool replies won't cause timeouts
    
    def execute(self, *commands):
        self._assert_empty_buffer()
        responses = []
        for command in commands:
            self._serial_port.write(bytes(command+'\n', encoding='ascii'))
            response = self._serial_port.read_until(b'>')[:-1] # see if there was any output
            responses.append(str(response, encoding='ascii') if response else None)
        if len(commands) == 1:
            responses = responses[0]
        self._assert_empty_buffer()
        return responses

    def _assert_empty_buffer(self):
        buffered = self._serial_port.read_all_buffered()
        if buffered:
            raise RuntimeError('Unexpected IOTool output: {}'.format(str(buffered, encoding='ascii')))
    
    def store_program(self, *commands):
        all_commands = ['program'] + list(commands) + ['end']
        responses = self.execute(*all_commands)
        errors = ['{}: {}'.format(command, response) for command, response in zip(all_commands, responses) if response is not None]
        if errors:
            raise RuntimeError('Program errors:\n'+'\n'.join(errors))
    
    def start_program(self, *commands, iters=1):
        if commands:
            self.store_program(*commands)
        else:
            self._assert_empty_buffer()
        self._serial_port.write('run {}\n'.format(iters).encode('ascii'))
    
    def wait_for_serial_char(self):
        self._serial_port.read(1)
    
    def _wait_for_program_done(self):
        return self._serial_port.read_until(b'>')[:-1]
    
    def wait_for_program_done(self):
        try:
            return self._wait_for_program_done()
        except KeyboardInterrupt as k:
            self.stop_program()
            raise k
        
    def stop_program(self):
        self.stop()
        self._wait_for_program_done()
        
    def stop(self):
        self._serial_port.write(b'!')
    
