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

class Response:
    """A container for a value to be provided by a background thread at some
    point in the future.

    To provide the response, the background thread simply calls the object with
    the value to pass back. To receive the response, the foreground thread
    calls wait().

    Foreground Thread:
    res = Response()
    bg_thread.send(res) # pass the Response to the background thread somehow
    value = res.wait()

    Background Thread:
    res = receive() # receive the response.
    res(value)

    """
    def __init__(self):
        self.ready = threading.Event()

    def __call__(self, response):
        self.response = response
        self.ready.set()

    def wait(self):
        self.ready.wait()
        return self.response

class AsyncDevice:
    """A class that uses a message_manager.MessageManager to deal with sending
    and receiving messages to and from some outside hardware device, potentially
    in async mode."""

    def __init__(self, message_manager):
        self._pending_responses = set()
        self._async = False
        self._message_manager = message_manager

    def wait(self):
        """Wait on all pending responses."""
        while self._pending_responses:
            response = self._pending_responses.pop()
            response.wait()

    def has_pending(self):
        """Return true if there are any responses to async messages still pending."""
        for response in self._pending_responses:
            # if any response is not ready, we know we're still pending
            if not response.ready.is_set():
                return True
        # all responses must be ready if we get to this point...
        return False

    def set_async(self, async):
        """If in async mode, send_message() returns None immediately; otherwise
        it waits for the device to finish before returning the response value."""
        if self._async and not async: # if setting async from True to False...
            self.wait() # ... don't let any pending events still be outstanding
        self._async = async

    def get_async(self):
        return self._async

    def send_message(self, message, async=None, response=None, coalesce=True):
        """Send the given message through the MessageManager.
        If the parameter 'async' is not None, it will override the async mode
        set with set_async(). If parameter 'response' is provided, that will
        be used as the response callback object.
        If 'coalesce' is False, then mutliple messages that generate the same
        response will be handled separately (good if the messages sent don't
        cancel the previous ones). If 'coalesce' is True, then messages with
        the same expected response will all be handled with the first response
        (good if subsequent messages cancel the previous ones and only one
        response is generated)."""
        response_key = self._generate_response_key(message)
        if response is None:
            response = Response()
        self._message_manager.send_message(message, response_key, response, coalesce=coalesce)
        if async or (async is None and self._async):
            self._pending_responses.add(response)
        else:
            return response.wait()

    def _generate_response_key(self, message):
        """Subclasses must implement a method to generate the appropriate
        response key so that the message_manager can match responses to the
        original messages."""
        raise NotImplementedError()

class EchoAsyncDevice(AsyncDevice):
    """For debugging purposes, a device that simply expects responses to be echoed back messages."""
    def _generate_response_key(self, message):
        return message

LeicaResponseTuple = collections.namedtuple('LeicaResponse', ['full_response', 'auto_event', 'header', 'error_code', 'response'])

def parse_leica_response(full_response):
    """Parse a line from the Leica's serial output."""
    header, *response = full_response.split(' ', 1)
    if len(response) == 0:
        response = None
    else:
        response = response[0]
    if header.startswith('$'):
        auto_event = True
        header = header[1:]
    else:
        auto_event = False
    error_code = header[2]
    return LeicaResponseTuple(full_response, auto_event, header, error_code, response)

class LeicaError(RuntimeError):
    """Leica communications error that can optionally stash a copy of a LeicaResponse object."""
    def __init__(self, *args, response=None):
        super().__init__(*args)
        self.response = response

class LeicaResponse(Response):
    """Response subclass that unpacks a Leica-format response into a namedtuple with the following fields:
    full_response: the entire response string
    auto_event: if the response was auto-generated from an event (i.e. prefixed with a '$')
    header: the function unit, error code, and command name
    error_code: just the error code
    response: everything after the header.

    If an error code was generated, raise a LeicaError on wait(). If constructed
    with an 'intent' help text, this will help create a better LeicaError.
    """
    def __init__(self, intent=None):
        super().__init__()
        self.intent = intent

    def __call__(self, full_response):
        super().__call__(parse_leica_response(full_response))

    def wait(self):
        response = super().wait()
        if response.error_code != '0':
            if self.intent is not None:
                error_text = 'Could not {} (error response "{}")'.format(self.intent, response.full_response)
            else:
                error_text = 'Error from microscope: "{}"'.format(response.full_response)
            raise LeicaError(error_text, response=response)
        return response


class LeicaAsyncDevice(AsyncDevice):
    """Base class for Leica function units. Responses keys are the function unit and
    command IDs from the outgoing message; the error state (message[2]) is ignored
    for the purposes of matching responses to commands."""

    def __init__(self, message_manager):
        super().__init__(message_manager)
        self._setup_device()
        self._adapter_callbacks = {}

    def _setup_device(self):
        """Override in subclasses to perform device-specific setup."""
        pass

    def send_message(self, command, *params, async=None, intent=None, coalesce=True):
        """Send a message to the Leica microscope

        Arguments:
            command: the command number for the Leica scope
            *params: a list of params to be coerced to strings and listed after command, separated by spaces
            async: if not None, override the async instance variable.
            intent: should be helpful text describing the intent of the command.
            coalesce: see AsyncDevice.send_message documentation.

        If a nonzero error code is returned, a LeicaError will be raised with
        the intent text when the response's wait() method is called.
        """
        message = ' '.join([str(command)] + [str(param) for param in params]) + '\r'
        response = LeicaResponse(intent)
        return super().send_message(message, async, response=response, coalesce=coalesce)

    def _generate_response_key(self, message):
        # return the message's function unit ID and command ID
        return message[:2] + message[3:5]

    def register_event_callback(self, event_id, callback):
        """If specific event information is enabled (via a separate message), then
        events with the given ID will cause a LeicaResponseTuple to be passed
        to the callback."""
        def adapter_callback(full_response):
            callback(parse_leica_response(full_response))
        self._adapter_callbacks[callback] = adapter_callback
        response_key = '$' + str(event_id)
        self._message_manager.register_persistent_callback(response_key, adapter_callback)

    def unregister_event_callback(self, event_id, callback):
        """Stop calling the given callback when events with the given ID occur."""
        adapter_callback = self._adapter_callbacks[callback]
        response_key = '$' + str(event_id)
        self._message_manager.unregister_persistent_callback(response_key, adapter_callback)

class AsyncDeviceNamespace:
    """Simple container class for building a hierarchy of AsyncDevice-like
    objects which have wait() and set_async() methods. This container
    implements wait() and set_async() methods that simply call the same on
    every object placed into its namespace.

    Toy example:
        scope = AsyncDeviceNamespace()
        scope.stage = LeicaDM6000Stage()
        scope.condensor = LeicaDM6000Condensor()
        scope.set_async(True)
        scope.stage.set_position(10,10,10)
        scope.condensor.set_field(7)
        scope.wait()
    """
    def __init__(self):
        self._children = set()

    @staticmethod
    def _is_async_capable(obj):
        for async_func in ('wait', 'set_async', 'get_async'):
            if not hasattr(obj, async_func):
                return False
        return True

    def __setattr__(self, name, value):
        if self._is_async_capable(value):
            self._children.add(name)
        super().__setattr__(name, value)

    def __delattr__(self, name):
        if self._is_async_capable(value):
            self._children.remove(name)
        super().__delattr__(name)

    def wait(self):
        for child in self._children:
            getattr(self, child).wait()

    def set_async(self, async):
        for child in self._children:
            getattr(self, child).set_async(async)

    def get_async(self):
        asyncs = [getattr(self, child).get_async() for child in self._children]
        if all(async == True for async in asyncs):
            return True
        elif all(async == False for async in asyncs):
            return False
        else:
            return "child devices have mixed async status"
