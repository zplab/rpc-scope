import threading
import zmq
import time
import os
import signal

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
        error_signal: signal number to use to produce an error in the foreground thread.
        error_text: text of error to raise when no heartbeat was detected.
    """
    def __init__(self, interval_sec, max_missed, error_signal=signal.SIGUSR1, error_text='Heartbeat not detected'):
        super().__init__(daemon=True)
        self.interval_sec = interval_sec
        self.max_missed = max_missed
        self.missed = 0
        self.error_signal = error_signal
        self.error_text = error_text
        self.old_handler = signal.signal(error_signal, self.handler)
        self.running = True
        self.armed = False
        self.start()

    def run(self):
        while self.running:
            if self._receive_beat():
                self.missed = 0
            else:
                self.missed += 1
            if self.armed and self.missed == self.max_missed:
                os.kill(os.getpid(), self.error_signal)
                break

    def handler(self, sig, stackframe):
        if self.old_handler is not None:
            signal.signal(self.error_signal, self.old_handler)
        raise RuntimeError(self.error_text)

    def _receive_beat(self):
        "if a heartbeat is received within self.interval_sec, return True, otherwise False"
        raise NotImplementedError()


class ZMQClient(Client):
    def __init__(self, port, interval_sec, max_missed, error_text=error_signal=signal.SIGUSR1, context=None):
        """HeartbeatClient subclass that uses ZeroMQ PUB/SUB to receive beats.

        Parameters:
            port: a string ZeroMQ port identifier, like 'tcp://127.0.0.1:5555'.
            interval_sec: interval to check for heartbeats. Should be larger than the server's interval.
            max_missed: maximum missed heartbeats before raising an error.
            error_signal: signal number to use to produce an error in the foreground thread.
            context: a ZeroMQ context to share, if one already exists.
        """
        self.context = context if context is not None else zmq.Context()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.RCVTIMEO = 1000 * interval_sec
        self.socket.LINGER = 0
        self.socket.SUBSCRIBE = ''
        self.socket.connect(port)
        super().__init__(interval_sec, max_missed, error_signal, error_text)

    def run(self):
        try:
            super().run()
        finally:
            self.socket.close()

    def _receive_beat(self):
        try:
            self.socket.recv()
            return True
        except zmq.error.Again:
            return False
