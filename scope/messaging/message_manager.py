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
# Authors: Zach Pincus, Erik Hvatum

import threading
import collections

from ..util import logging
logger = logging.get_logger(__name__)

from ..util import smart_serial

class MessageManager(threading.Thread):
    """Base class for managing messages and responses sent to/from a
    device that can operate asynchronously and may respond out-of-order.

    This class maintains a dictionary of callbacks for pending responses,
    indexed by "response keys". When a response is received that matches the key,
    the callback is called.

    Subclasses must implement a method for generating a response key from an
    incoming response, as well as methods for sending and receiving messages.
    Message sending is done from a separate thread.

    This class is a thread that starts itself running in the background upon
    construction, by default in daemonic form so that it will close itself
    on exit.

    To cause the thread to stop running, set the 'running' attribute to False.
     """
    thread_name = 'MessageManager'

    def __init__(self, daemon=True):
        # pending_responses holds lists of callbacks to call for each response key
        self.pending_grouped_responses = collections.defaultdict(list)
        self.pending_standalone_responses = collections.defaultdict(list)
        super().__init__(name=self.thread_name, daemon=daemon)
        self.start()

    def run(self):
        """Thread target: do not call directly."""
        self.running = True
        while self.running: # better than 'while True' because can alter self.running from another thread
            response = self._receive_message()
            if response is None:
                break
            response_key = self._generate_response_key(response)
            logger.debug('received response: {} with response key: {}', response, response_key)

            handled = False
            if response_key in self.pending_grouped_responses:
                callbacks = self.pending_grouped_responses.pop(response_key)
                for callback, onetime in callbacks:
                    callback(response)
                    if not onetime:
                        self.pending_responses[response_key].append((callback, onetime))
                handled = True

            if response_key in self.pending_standalone_responses:
                callback, *remaining_callbacks = self.pending_standalone_responses.pop(response_key)
                callback(response)
                if remaining_callbacks:
                    self.pending_standalone_responses[response] = remaining_callbacks
                handled = True

            if not handled:
                self._handle_unexpected_response(response, response_key)

    def send_message(self, message, response_key=None, response_callback=None, onetime=True, coalesce=True):
        """Send a message from a foreground thread.
        (I.e. not the thread that the MessageManager is running.)

        Arguments
        message: message to send.
        response_key: if provided, any response with a matching response key will cause
            the provided response_callback to be called with the full response value.
        onetime: if True, the callback will be called only the first time a matching
            response is received. Otherwise, it will be called every time.
        coalesce: if True, this callback may be called at the same time as a
            previously queued callback, in response to a previously sent
            message. (This makes sense if messages override each other and the
            first response should be considered to retire both.) If False, this
            callback will not be grouped with any other callbacks also queued
            with 'coalesce=False'. Note that 'onetime' cannot be False if
            'coalesce' is False.
        """
        # There is one thread-synchronization worry: if a pending response is
        # queued right before a response to a previous message with the same
        # response key is handled, but before this current message is sent (which
        # would otherwise override the previous message), then this callback will
        # be called for the previous response (if coalesce=True), leaving the
        # current message with no handler.
        # Solution: do not queue and send messages while response-handling is
        # in progress. The problem is that a previous-response could be in-flight
        # over the wire, which cannot be detected, and so we can't 100% avoid
        # these types of cases! This is a design flaw in the Leica system, for
        # which this infrastructure is built. The best solution is to process
        # things as quickly as possible on this side, so we will not use any
        # locking primitives and just hope for the best.

        logger.debug('sending message: {!r} with response key: {!r}', message, response_key)
        if response_key is not None and response_callback is not None:
            assert(onetime or coalesce)
            if coalesce:
                self.pending_grouped_responses[response_key].append((response_callback, onetime))
            else:
                self.pending_standalone_responses[response_key].append(response_callback)
        self._send_message(message)

    def _send_message(self, message):
        """Send a message to the device from a foreground thread."""
        raise NotImplementedError()

    def _receive_message(self, message):
        """Block until a message is received. Return None if an error-condition
        occurs during the read and the run() loop should be terminated."""
        raise NotImplementedError()

    def _generate_response_key(self, response):
        """Generate an appropriate response key from an incoming message."""
        raise NotImplementedError()

    def _handle_unexpected_response(self, response, response_key):
        """Handle a response that could not be matched to a response key."""
        logger.debug('received UNPROMPTED response: {} with response key: {}', response, response_key)

class SerialMessageManager(MessageManager):
    """MessageManager subclass that sends and receives from a serial port."""
    def __init__(self, serial_port, serial_baud, response_terminator, daemon=True):
        """Arguments:
            serial_port, serial_baud: information for connecting to serial device
            response_terminator: byte or bytes that terminate a response message
            daemon: quit running in the background automatically when the interpreter is exited
                    (otherwise must set self.running to False to quit)"""
        # need a timeout on the serial port so that _receive_message can
        # occasionally check its 'running' attribute to decide if it needs to return.
        self.serial_port = smart_serial.Serial(serial_port, baudrate=serial_baud, timeout=1)
        self.thread_name = 'SerialMessageManager({})'.format(self.serial_port.port)
        self.response_terminator = response_terminator
        super().__init__(daemon)

    def _send_message(self, message):
        if type(message) != bytes:
            message = bytes(message, encoding='ascii')
        self.serial_port.write(message)

    def _receive_message(self):
        while self.running:
            try:
                response = self.serial_port.read_until(self.response_terminator)
            except smart_serial.SerialTimeout:
                continue
            return str(response[:-len(self.response_terminator)], encoding='ascii')

class LeicaMessageManager(SerialMessageManager):
    """MessageManager subclass appropriate for routing messages from Leica API"""
    def __init__(self, serial_port, serial_baud, daemon=True):
        super().__init__(serial_port, serial_baud, response_terminator=b'\r', daemon=daemon)

    def _generate_response_key(self, response):
        if response[0] == '$':
            # response is a status update: return entire function id
            return response[:6]
        else:
            # Return function unit ID and command ID, but strip out
            # the error code so can match both error and non-error responses
            return response[:2] + response[3:5]

    def _handle_unexpected_response(self, response, response_key):
        if response[0] == '$':
            # Unexpected notifications are quite common, and if the dm6000b has communicated with MicroManager or the Leica
            # Windows software since last power cycled, they may be overwhelming in number. Therefore, these are appropriately
            # debug messages.
            logger.debug('received UNEXPECTED notification from Leica device: {} with response key: {}', response, response_key)
        else:
            # Unprompted command responses are an ominous sign and are of general interest
            logger.warn('received UNPROMPTED COMMAND RESPONSE from Leica device: {} with response key: {}', response, response_key)
