import time
from . import commands

class PedalWaiter:
    def __init__(self, pin, iotool, pressed_is_high=True, bounce_time=0.1):
        self.last_time = 0
        self.iotool = iotool
        self.bounce_time = bounce_time
        self.delay = commands.delay_ms(int(self.bounce_time * 1000))
        if pressed_is_high:
            self.depress = commands.wait_high(pin)
            self.release = commands.wait_low(pin)
        else:
            self.depress = commands.wait_low(pin)
            self.release = commands.wait_high(pin)
    
    def _wait(self, command):
        sleep_time = bounce_time - (time.time() - self.last_time)
        if sleep_time > 0:
            time.sleep(sleep_time)
        self.iotool.start_program(command)
        self.iotool.wait_for_program_done()
        self.last_time = time.time()
        
    def wait_depress(self):
        self._wait(self.depress)
    
    def wait_release(self):
        self._wait(self.release)
    
    def wait_click(self):
        self.iotool.start_program(self.depress, self.delay, self.release)
        self.iotool.wait_for_program_done()
        self.last_time = time.time()
