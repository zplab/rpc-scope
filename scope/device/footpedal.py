# This code is licensed under the MIT License (see LICENSE file for details)

import time
from ..config import scope_configuration

class Footpedal:
    def __init__(self, iotool):
        config = scope_configuration.get_config()
        pin = config.iotool.FOOTPEDAL_PIN
        bounce_ms = config.iotool.FOOTPEDAL_BOUNCE_DELAY_MS
        self._last_time = 0
        self._iotool = iotool
        self._bounce_sec = bounce_ms / 1000
        self._delay = iotool.commands.delay_ms(int(bounce_ms))
        if config.iotool.FOOTPEDAL_CLOSED_TTL_STATE:
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
        self._iotool.wait_until_done()
        self._last_time = time.time()
