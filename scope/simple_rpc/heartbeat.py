# This code is licensed under the MIT License (see LICENSE file for details)

import threading
import zmq
import time

class Server(threading.Thread):
    """Server for publishing heartbeats.
    """
    def __init__(self, interval_sec):
        super().__init__(daemon=True)
        self.interval_sec = interval_sec
        self.running = True
        self.start()

    def run(self):
        while self.running:
            time.sleep(self.interval_sec)
            self._beat(int(time.time()))

    def _beat(self, payload):
        raise NotImplementedError()

class ZMQServer(Server):
    def __init__(self, port, interval_sec, context=None):
        """HeartbeatServer subclass that uses ZeroMQ PUB/SUB to send out beats.

        Parameters:
            port: a string ZeroMQ port identifier, like 'tcp://127.0.0.1:5555'.
            interval_sec: heartbeat interval, in seconds
            context: a ZeroMQ context to share, if one already exists.
        """
        self.context = context if context is not None else zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.bind(port)
        super().__init__(interval_sec)

    def run(self):
        try:
            super().run()
        finally:
            self.socket.close()

    def _beat(self, payload):
        self.socket.send(str(payload).encode('utf-8'))

class Client(threading.Thread):
    """Client for receiving and producing errors on heartbeats / missing beats, respectively.

    Parameters:
        interval_sec: interval to check for heartbeats. Should be larger than the server's interval.
        max_missed: maximum missed heartbeats before raising an error.
        error_callback: function to call on heartbeat error.
    """
    def __init__(self, interval_sec, max_missed, error_callback, clear_callback):
        super().__init__(daemon=True)
        self.interval_sec = interval_sec
        self.max_missed = max_missed
        self.missed = 0
        self.error_callback = error_callback
        self.clear_callback = clear_callback
        self.running = True
        self.start()

    def run(self):
        while True:
            beat = self._receive_beat()
            if not self.running:
                break
            elif beat: # we did receive a heartbeat
                if self.missed >= self.max_missed:
                    self.clear_callback()
                self.missed = 0
            else:
                self.missed += 1
            if self.missed >= self.max_missed:
                self.error_callback()

    def stop(self):
        self.running = False
        self.join()

    def _receive_beat(self):
        """if a heartbeat is received within self.interval_sec, return True, otherwise False.
        If self.running goes to False, return ASAP"""
        raise NotImplementedError()


class ZMQClient(Client):
    def __init__(self, addr, interval_sec, max_missed, error_callback, clear_callback, context=None):
        """HeartbeatClient subclass that uses ZeroMQ PUB/SUB to receive beats.

        Parameters:
            addr: a string ZeroMQ port identifier, like 'tcp://127.0.0.1:5555'.
            interval_sec: interval to check for heartbeats. Should be larger than the server's interval.
            max_missed: maximum missed heartbeats before raising an error.
            error_signal: signal number to use to produce an error in the foreground thread.
            context: a ZeroMQ context to share, if one already exists.
        """
        self.context = context if context is not None else zmq.Context()
        self.addr = addr
        super().__init__(interval_sec, max_missed, error_callback, clear_callback)

    def run(self):
        self.socket = self.context.socket(zmq.SUB)
        self.socket.RCVTIMEO = 0 # we use poll to determine whether there's data to receive, so we don't want to wait on recv
        self.socket.LINGER = 0
        self.socket.SUBSCRIBE = ''
        self.socket.connect(self.addr)
        try:
            super().run()
        finally:
            self.socket.close()

    def _receive_beat(self):
        hearbeat_deadline = time.time() + self.interval_sec
        while self.running:
            if time.time() > hearbeat_deadline:
                return False
            if self.socket.poll(500): # 500 ms wait before checking self.running again
                # poll returns true of socket has data to recv
                self.socket.recv()
                return True
