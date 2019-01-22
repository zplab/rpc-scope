# This code is licensed under the MIT License (see LICENSE file for details)

import threading
import collections

from ..util import logging
logger = logging.get_logger(__name__)

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
    in async_ mode."""

    def __init__(self, message_manager):
        self._pending_responses = set()
        self._async_ = False
        self._message_manager = message_manager

    def wait(self):
        """Wait on all pending responses."""
        while self._pending_responses:
            response = self._pending_responses.pop()
            response.wait()

    def has_pending(self):
        """Return true if there are any responses to async_ messages still pending."""
        for response in self._pending_responses:
            # if any response is not ready, we know we're still pending
            if not response.ready.is_set():
                return True
        # all responses must be ready if we get to this point...
        return False

    def set_async_(self, async_):
        """If in async_ mode, send_message() returns None immediately; otherwise
        it waits for the device to finish before returning the response value."""
        if self._async_ and not async_: # if setting async_ from True to False...
            self.wait() # ... don't let any pending events still be outstanding
        self._async_ = async_

    def get_async_(self):
        return self._async_

    def send_message(self, message, async_=None, response=None, coalesce=True):
        """Send the given message through the MessageManager.

        If the parameter 'async_' is not None, it will override the async_ mode
        set with set_async_(). If 'async_' is the string 'fire_and_forget', then
        the command will be sent and NOT added to the pending responses. Use
        with caution.

        If parameter 'response' is provided, that will be used as the response
        callback object.

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
        if async_ == 'fire_and_forget':
            return
        if async_ or (async_ is None and self._async_):
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
    def __init__(self, message, intent=None):
        super().__init__()
        self.message = message
        self.intent = intent

    def __call__(self, full_response):
        response = parse_leica_response(full_response)
        if response.error_code != '0':
            logger.warning('Microscope error. (message to scope: "{}", error response: "{}")', self.message, response.full_response)
        super().__call__(response)

    def wait(self):
        response = super().wait()
        if response.error_code != '0':
            if self.intent is not None:
                error_text = 'Could not {} (message to scope: "{}", error response: "{}")'.format(self.intent, self.message, response.full_response)
            else:
                error_text = 'Microscope error (message to scope: "{}", error response: "{}")'.format(self.message, response.full_response)
            raise LeicaError(error_text, response=response)
        return response


class LeicaAsyncDevice(AsyncDevice):
    """Base class for Leica function units. Responses keys are the function unit and
    command IDs from the outgoing message; the error state (message[2]) is ignored
    for the purposes of matching responses to commands."""

    def __init__(self, message_manager):
        super().__init__(message_manager)
        self._adapter_callbacks = {}
        self._setup_device()

    def _setup_device(self):
        """Override in subclasses to perform device-specific setup."""
        pass

    def send_message(self, command, *params, async_=None, intent=None, coalesce=True):
        """Send a message to the Leica microscope

        Parameters:
            command: the command number for the Leica scope
            *params: a list of params to be coerced to strings and listed after command, separated by spaces
            async_: if not None, override the async_ instance variable.
            intent: should be helpful text describing the intent of the command.
            coalesce: see AsyncDevice.send_message documentation.

        If a nonzero error code is returned, a LeicaError will be raised with
        the intent text when the response's wait() method is called.
        """
        message = ' '.join([str(command)] + [str(param) for param in params]) + '\r'
        response = LeicaResponse(message[:-1], intent) # don't include \r from message...
        return super().send_message(message, async_, response=response, coalesce=coalesce)

    def _generate_response_key(self, message):
        # return the message's function unit ID and command ID
        return message[:2] + message[3:5]

    def _register_event_callback(self, event_id, callback):
        """If specific event information is enabled (via a separate message), then
        events with the given ID will cause a LeicaResponseTuple to be passed
        to the callback."""
        def adapter_callback(full_response):
            callback(parse_leica_response(full_response))
        self._adapter_callbacks[callback] = adapter_callback
        response_key = '$' + str(event_id)
        self._message_manager.register_persistent_callback(response_key, adapter_callback)

    def _unregister_event_callback(self, event_id, callback):
        """Stop calling the given callback when events with the given ID occur."""
        adapter_callback = self._adapter_callbacks[callback]
        response_key = '$' + str(event_id)
        self._message_manager.unregister_persistent_callback(response_key, adapter_callback)

class AsyncDeviceNamespace:
    """Simple container class for building a hierarchy of AsyncDevice-like
    objects which have wait() and set_async_() methods. This container
    implements wait() and set_async_() methods that simply call the same on
    every object placed into its namespace.

    Toy example:
        scope = AsyncDeviceNamespace()
        scope.stage = LeicaDM6000Stage()
        scope.condensor = LeicaDM6000Condensor()
        scope.set_async_(True)
        scope.stage.set_position(10,10,10)
        scope.condensor.set_field(7)
        scope.wait()
    """
    def __init__(self):
        self._children = set()

    @staticmethod
    def _is_async__capable(obj):
        for async__func in ('wait', 'set_async_', 'get_async_'):
            if not hasattr(obj, async__func):
                return False
        return True

    def __setattr__(self, name, value):
        if self._is_async__capable(value):
            self._children.add(name)
        super().__setattr__(name, value)

    def __delattr__(self, name):
        if self._is_async__capable(getattr(self, name)):
            self._children.remove(name)
        super().__delattr__(name)

    def wait(self):
        for child in self._children:
            getattr(self, child).wait()

    def set_async_(self, async_):
        for child in self._children:
            getattr(self, child).set_async_(async_)

    def get_async_(self):
        async_s = [getattr(self, child).get_async_() for child in self._children]
        if all(async_ is True for async_ in async_s):
            return True
        elif all(async_ is False for async_ in async_s):
            return False
        else:
            return "child devices have mixed async_ status"
