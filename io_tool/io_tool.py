from .. import messaging
from . import commands

class IOTool:
    def __init__(self, serial_port):
        self._serial_port = messaging.smart_serial.Serial(serial_port)
        self._serial_port.write(b'\x80\xFF\n') # disable echo
        self._serial_port.read(2) # read back echo of above (no other echoes will come)
        self.commands = commands

    def _send(self, commands):
        command_bytes = bytes('\n'.join(commands) + '\n', encoding='ascii')
        print(command_bytes)
        self._serial_port.write(command_bytes)
    
    def execute(self, *commands):
        self._send(commands)

    def assert_empty_buffer(self):
        buffered = self._serial_port.read_all_buffered()
        if buffered:
            raise RuntimeError('Unexpected IOTool output: {}'.format(str(buffered, encoding='ascii')))
    
    def store_program(self, *commands):
        self.assert_empty_buffer()
        self._send(['program'] + list(commands) + ['end'])
        response = self._serial_port.read_until(b'OK\r\n')[:-4] # see if there was any output before the 'OK'
        if response:
            raise RuntimeError('Program error: {}'.format(str(response, encoding='ascii')))
    
    def start_program(self, *commands, iters=1):
        self.assert_empty_buffer()
        if commands:
            self.store_program(*commands)
        self._serial_port.write(b'run {}\n'.format(iters))
    
    def wait_for_serial_char(self):
        self._serial_port.read(1)
    
    def _wait_for_program_done(self):
        return self._serial_port.read_until(b'DONE\r\n')[:-6]
    
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
    
