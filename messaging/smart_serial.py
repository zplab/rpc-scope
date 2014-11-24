import sys
import fcntl
import struct
import select
import os
import errno

import serial.serialposix as serialposix
from serial import SerialException

class SerialTimeout(SerialException):
    pass

class Serial(serialposix.PosixSerial):
    def __init__(self, port, baudrate=9600, timeout=None, **kwargs):
        self.read_buffer = b''
        super().__init__(port, baudrate=baudrate, timeout=timeout, **kwargs)

    def inWaiting(self):
        """Return the number of characters currently in the input buffer."""
        s = fcntl.ioctl(self.fd, serialposix.TIOCINQ, serialposix.TIOCM_zero_str)
        return struct.unpack('I',s)[0] + len(self.read_buffer)

    def read(self, size=1):
        """Read size bytes from the serial port. If a timeout occurs, an
           exception is raised. With no timeout it will block until the requested
           number of bytes is read. If interrupted by a timeout or
           KeyboardInterrupt, before 'size' bytes have been read, the pending
           bytes read will not be lost but will be available to subsequent read()
           calls."""
        if not self._isOpen: raise serialposix.portNotOpenError
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
                ready,_,_ = select.select([self.fd],[],[], self._timeout)
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
                    raise serialposix.SerialException('device reports readiness to read but returned no data (device disconnected or multiple access on port?)')
                self.read_buffer += buf
            except OSError as e:
                # ignore EAGAIN errors. all other errors are shown
                if e.errno != errno.EAGAIN:
                    raise serialposix.SerialException('read failed: %s' % (e,))

        read_buffer = self.read_buffer
        try:
            self.read_buffer = b''
            return read_buffer
        except KeyboardInterrupt as k:
            self.read_buffer = read_buffer
            raise k
    
    def read_all_buffered(self):
        return self.read(self.inWaiting())
    
    def read_until(self, match):
        """Read bytes from the serial until the sequence of bytes specified in
           'match' is read out. If a timeout is set and match hasn't been made,
           no bytes will be returned. With no timeout it will block until the
           match is made. If interrupted by a timeout or KeyboardInterrupt before
           the match is made, the pending bytes read will not be lost but will be
           available to subsequent read_until() calls."""
        if not self._isOpen: raise serialposix.portNotOpenError
        search_start = 0
        ml = len(match)
        while True:
            match_pos = self.read_buffer.find(match, search_start)
            if match_pos != -1:
                break
            search_start = len(self.read_buffer) - ml + 1
            try:
                ready,_,_ = select.select([self.fd],[],[], self._timeout)
                # If select was used with a timeout, and the timeout occurs, it
                # returns with empty lists -> thus abort read operation.
                # For timeout == 0 (non-blocking operation) also abort when there
                # is nothing to read.
                if not ready:
                    raise SerialTimeout()   # timeout
                s = fcntl.ioctl(self.fd, serialposix.TIOCINQ, serialposix.TIOCM_zero_str)
                in_waiting = struct.unpack('I',s)[0]
                buf = os.read(self.fd, max(in_waiting, ml))
                # read should always return some data as select reported it was
                # ready to read when we get to this point.
                if not buf:
                    # Disconnected devices, at least on Linux, show the
                    # behavior that they are always ready to read immediately
                    # but reading returns nothing.
                    raise serialposix.SerialException('device reports readiness to read but returned no data (device disconnected or multiple access on port?)')
                self.read_buffer += buf
            except OSError as e:
                # ignore EAGAIN errors. all other errors are shown
                if e.errno != errno.EAGAIN:
                    raise serialposix.SerialException('read failed: %s' % (e,))

        read_buffer = self.read_buffer
        match_last = match_pos + ml
        try:
            self.read_buffer = read_buffer[match_last:]
            return read_buffer[:match_last]
        except KeyboardInterrupt as k:
            self.read_buffer = read_buffer
            raise k