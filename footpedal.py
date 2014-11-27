import time
from . import scope_configuration as config

class Footpedal:
    def __init__(self, iotool):
        pin = config.IOTool.FOOTPEDAL_PIN
        bounce_ms = config.IOTool.FOOTPEDAL_BOUNCE_DELAY_MS
        self._last_time = 0
        self._iotool = iotool
        self._bounce_sec = bounce_ms / 1000
        self._delay = iotool.commands.delay_ms(int(bounce_ms))
        if config.IOTool.FOOTPEDAL_CLOSED_TTL_STATE:
            self._depress = iotool.commands.wait_high(pin)
            self._release = iotool.commands.wait_low(pin)
        else:
            self._depress = iotool.commands.wait_low(pin)
            self._release = iotool.commands.wait_high(pin)

    def _wait(self, command):
        sleep_time = self._bounce_sec - (time.time() - self._last_time)
        if sleep_time > 0:
            time.sleep(sleep_time)
        self._iotool.execute(command)
        self._last_time = time.time()

    def wait_depress(self):
        self._wait(self._depress)

    def wait_release(self):
        self._wait(self._release)

    def wait_click(self):
        self._iotool.start_program(self._depress, self._delay, self._release)
        self._iotool.wait_for_program_done()
        self._last_time = time.time()
