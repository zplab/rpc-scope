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

import time
from ..config import scope_configuration

class Footpedal:
    def __init__(self, iotool):
        config = scope_configuration.get_config()
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
        self._iotool.wait_until_done()
        self._last_time = time.time()
