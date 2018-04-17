# This code is licensed under the MIT License (see LICENSE file for details)

import threading

class Timer(threading.Thread):
    def __init__(self, function, interval, run_immediately=True, *args, **kws):
        super().__init__(daemon=True)
        self.function = function
        self.args = args
        self.kws = kws
        self.stopped = threading.Event()
        self.interval = interval
        self.run_immediately = run_immediately
        self.start()

    @property
    def is_running(self):
        return not self.stopped.is_set()

    def stop(self):
        self.stopped.set()

    def run(self):
        if self.run_immediately:
            self.function(*self.args, **self.kws)
        while not self.stopped.wait(self.interval):
            self.function(*self.args, **self.kws)