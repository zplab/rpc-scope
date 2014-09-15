import threading
import serial
import time
import random

"""Debugging 'device' that just asynchronously echoes its inputs back, randomly delayed."""

class DelayedResponse(threading.Thread):
    def __init__(self, line, lock, serialport, max_delay=5):
        super().__init__()
        self.line = line
        self.lock = lock
        self.serialport = serialport
        self.max_delay = max_delay
    
    def run(self):
        time.sleep(random.random()*self.max_delay)
        self.lock.acquire()
        print("sending", self.line)
        self.serialport.write(self.line)
        self.lock.release()

def main(port):
    serialport = serial.Serial(port)
    lock = threading.Lock()
    while True:
        try:
            line = serialport.readline()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            continue
        print("received", line)
        DelayedResponse(line, lock, serialport).start()


if __name__ == '__main__':
    import sys
    port = '/dev/ptyp0' if len(sys.argv) == 1 else sys.argv[1]
    print("starting echo device on", port)
    main(port)