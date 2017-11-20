# This code is licensed under the MIT License (see LICENSE file for details)

import sys
import select
import os
import errno
import time

import serial
import serial.serialposix as serialposix

SerialException = serial.SerialException
class SerialTimeout(SerialException):
    pass

class Serial(serialposix.Serial):
    """Serial port class that differs from the pyserial library in three
    key ways:
    (1) Read timeouts raise an exception rather than just returning less
    data than requested. This makes it easier to detect error conditions.
    (2) A blocking read() or read_until() command will not lose any data
    already read if a timeout or KeyboardInterrupt occurs during the read.
    Instead, the next time the read function is called, the data already
    read in will still be there.
    (3) A read_until() command is provided that reads from the serial port
    until some string is matched.
    """
    def __init__(self, port, **kwargs):
        self.read_buffer = b''
        super().__init__(port, **kwargs)

    @serialposix.Serial.in_waiting.getter
    def in_waiting(self):
        """Return the number of characters currently in the input buffer."""
        return serialposix.Serial.in_waiting.fget(self) + len(self.read_buffer)

    def read(self, size=1):
        """Read size bytes from the serial port. If a timeout occurs, an
           exception is raised. With no timeout it will block until the requested
           number of bytes is read. If interrupted by a timeout or
           KeyboardInterrupt, before 'size' bytes have been read, the pending
           bytes read will not be lost but will be available to subsequent read()
           calls."""
        if not self.is_open: raise serialposix.portNotOpenError
        if len(self.read_buffer) > size:
            read_buffer = self.read_buffer
            try:
                self.read_buffer = read_buffer[size:]
                return read_buffer[:size]
            except KeyboardInterrupt as k:
                self.read_buffer = read_buffer
                raise k
        while len(self.read_buffer) < size:
            try:
                ready,_,_ = select.select([self.fd],[],[], self.timeout)
                # If select was used with a timeout, and the timeout occurs, it
                # returns with empty lists -> thus abort read operation.
                # For timeout == 0 (non-blocking operation) also abort when there
                # is nothing to read.
                if not ready:
                    raise SerialTimeout()   # timeout
                buf = os.read(self.fd, size-len(self.read_buffer))
                # read should always return some data as select reported it was
                # ready to read when we get to this point.
                if not buf:
                    # Disconnected devices, at least on Linux, show the
                    # behavior that they are always ready to read immediately
                    # but reading returns nothing.
                    raise SerialException('device reports readiness to read but returned no data (device disconnected or multiple access on port?)')
                self.read_buffer += buf
            except OSError as e:
                # because SerialException is a IOError subclass, which is a OSError subclass,
                # we could accidentally catch and re-raise SerialExceptions we ourselves raise earlier
                # which is a tad silly.
                if isinstance(e, SerialException):
                    raise

                # ignore EAGAIN errors. all other errors are shown
                if e.errno != errno.EAGAIN:
                    raise SerialException('read failed: %s' % (e,))

        read_buffer = self.read_buffer
        try:
            self.read_buffer = b''
            return read_buffer
        except KeyboardInterrupt as k:
            self.read_buffer = read_buffer
            raise k

    def clear_input_buffer(self):
        while self.in_waiting:
            if len(self.read_all()) > 0:
                time.sleep(0.01)

    def read_until(self, match):
        """Read bytes from the serial until the sequence of bytes specified in
           'match' is read out. If a timeout is set and match hasn't been made,
           no bytes will be returned. With no timeout it will block until the
           match is made. If interrupted by a timeout or KeyboardInterrupt before
           the match is made, the pending bytes read will not be lost but will be
           available to subsequent read_until() calls."""
        if not self.is_open: raise serialposix.portNotOpenError
        search_start = 0
        ml = len(match)
        while True:
            match_pos = self.read_buffer.find(match, search_start)
            if match_pos != -1:
                break
            search_start = len(self.read_buffer) - ml + 1
            try:
                ready,_,_ = select.select([self.fd],[],[], self.timeout)
                # If select was used with a timeout, and the timeout occurs, it
                # returns with empty lists -> thus abort read operation.
                # For timeout == 0 (non-blocking operation) also abort when there
                # is nothing to read.
                if not ready:
                    raise SerialTimeout()   # timeout
                in_recv_buffer = serialposix.Serial.in_waiting.fget(self) # call the superclass property getter...
                buf = os.read(self.fd, in_recv_buffer)
                # read should always return some data as select reported it was
                # ready to read when we get to this point.
                if not buf:
                    # Disconnected devices, at least on Linux, show the
                    # behavior that they are always ready to read immediately
                    # but reading returns nothing.
                    raise SerialException('device reports readiness to read but returned no data (device disconnected or multiple access on port?)')
                self.read_buffer += buf
            except OSError as e:
                # because SerialException is a IOError subclass, which is a OSError subclass,
                # we could accidentally catch and re-raise SerialExceptions we ourselves raise earlier
                # which is a tad silly.
                if isinstance(e, SerialException):
                    raise

                # ignore EAGAIN errors. all other errors are shown
                if e.errno != errno.EAGAIN:
                    raise SerialException('read failed: %s' % (e,))

        read_buffer = self.read_buffer
        match_last = match_pos + ml
        try:
            self.read_buffer = read_buffer[match_last:]
            return read_buffer[:match_last]
        except KeyboardInterrupt as k:
            self.read_buffer = read_buffer
            raise k
