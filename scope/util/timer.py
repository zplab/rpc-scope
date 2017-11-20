# This code is licensed under the MIT License (see LICENSE file for details)

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
        while not self._stopped.wait(self.interval):
            self.callback()