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

class Timer(threading.Thread):
    def __init__(self, callback, interval, run_immediately=True):
        super().__init__(daemon=True)
        self.callback = callback
        self._stopped = threading.Event()
        self.interval = interval
        self.run_immediately = run_immediately
        self.start()

    @property
    def running(self):
        return self._stopped.is_set()

    @running.setter
    def running(self, value):
        if not running:
            self._stopped.set()

    def run(self):
        if self.run_immediately:
            self.callback()
        while not self.stopped.wait(self.interval):
            self.callback()