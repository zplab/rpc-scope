import threading
import collections

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
    
    def __setattr__(self, name, value):
        if not name.startswith('_'):
            self._children.add(name)
        super().__setattr__(name, value)
    
    def __delattr__(self, name):
        if not name.startswith('_'):
            self._children.remove(name)
        super().__delattr__(name)
    
    def wait(self):
        for child in self._children:
            getattr(self, child).wait()
    
    def set_async(self, async):
        for child in self._children:
            getattr(self, child).set_async(async)

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

LeicaResponseTuple = collections.namedtuple('LeicaResponse', ['full_response', 'auto_event', 'header', 'error_code', 'response'])

class LeicaResponse(Response):
    def __call__(self, full_response):
        header, response = full_response.split(' ')
        if header.startswith('$'):
            auto_event = True
            header = header[1:]
        else:
            auto_event = False
        error_code = header[2]
        super().__call__(LeicaResponseTuple(full_response, auto_event, header, error_code, response))
        

class AsyncDevice:
    """A class that uses a message_manager.MessageManager to deal with sending 
    and receiving messages to and from some outside hardware device, potentially 
    in async mode."""
    
    def __init__(self, message_manager):
        self._pending_responses = set()
        self._async = False
        self._message_manager = message_manager
        self._response_class = Response
    
    def wait(self):
        """Wait on all pending responses."""
        while self._pending_responses:
            response = self._pending_responses.pop()
            response.wait()
    
    def set_async(self, async):
        """If in async mode, send_message() returns None immediately; otherwise 
        it waits for the device to finish before returning the response value."""
        self._async = async
    
    def send_message(self, message, async=None):
        """Send the given message through the MessageManager.
        If the parameter 'async' is not None, it will override the async mode
        set with set_async()."""
        response_key = self._generate_response_key(message)
        response = self._response_class()
        self._message_manager.send_message(message, response_key, response)
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

class LeicaAsyncDevice(AsyncDevice):
    """Base class for Leica function units. Responses keys are the function unit and
    command IDs from the outgoing message; the error state (message[2]) is ignored
    for the purposes of matching responses to commands."""
    
    def __init__(self, message_manager):
        super().__init__(message_manager)
        self._response_class = LeicaResponse
        self._setup_device()
    
    def _setup_device(self):
        """Override in subclasses to perform device-specific setup."""
        pass
    
    def send_message(self, command, *params, async=None):
        message = ' '.join([command] + [str(param) for param in params])
        return super().send_message(message, async)
        
    
    def _generate_response_key(self, message):
        # return the message's function unit ID and command ID
        return message[:2] + message[3:5]

class LeicaError(RuntimeError):
    pass