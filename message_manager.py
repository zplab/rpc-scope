import threading
import collections

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
    
    def __init__(self, verbose=False, daemon=True):
        # pending_responses holds lists of callbacks to call for each response key
        self.pending_responses = collections.defaultdict(list)
        self.verbose = verbose
        super().__init__(name=self.thread_name, daemon=daemon)
        self.start()
    
    def run(self):
        """Thread target: do not call directly."""
        self.running = True
        while self.running: # better than 'while True' because can alter self.running from another thread
            response = self._receive_message()
            response_key = self._generate_response_key(response)
            if response_key in self.pending_responses:
                callbacks = self.pending_responses.pop(response_key, [])
                if self.verbose:
                    print('received response: {} with response key: {} ({} callbacks)'.format(response, response_key, len(callbacks)))
                for callback, onetime in callbacks:
                    callback(response)
                    if not onetime:
                        self.pending_responses[response_key].append((callback, onetime))
            else:
                self._handle_unexpected_response(response, response_key)
    
    def send_message(self, message, response_key=None, response_callback=None, onetime=True):
        """Send a message from a foreground thread.
        (I.e. not the thread that the MessageManager is running.)
        
        Arguments
        message: message to send.
        response_key: if provided, any response with a matching response key will cause
            the provided callback to be called with the full response value.
        """
        # don't worry about thread synchronization between message-sending and -receiving
        # threads. Dict getting and list appending are atomic.
        if self.verbose:
            print('sending message: {!r} with response key: {!r}'.format(message, response_key))
        if response_key is not None and response_callback is not None:
            self.pending_responses[response_key].append((response_callback, onetime))
        self._send_message(message)
        
    def _send_message(self, message):
        """Send a message to the device from a foreground thread."""
        raise NotImplementedError()

    def _receive_message(self, message):
        """Block until a message is received."""
        raise NotImplementedError()
    
    def _generate_response_key(self, response):
        """Generate an appropriate response key from an incoming message."""
        raise NotImplementedError()

    def _handle_unexpected_response(self, response, response_key):
        """Handle a response that could not be matched to a response key."""
        if self.verbose:
            print('received UNPROMPTED response: {} with response key: {}'.format(response, response_key))

class SerialMessageManager(MessageManager):
    """MessageManager subclass that sends and receives from a serial port."""
    def __init__(self, serialport, response_terminator, verbose=False, daemon=True):
        """Arguments:
            serialport: initialized serial.Serial-like object
            response_terminator: byte or bytes that terminate a response message
            daemon: quit running in the background automatically when the interpreter is exited
                    (otherwise must set self.running to False to quit)"""
        self.serialport = serialport
        self.thread_name = 'SerialMessageManager({})'.format(serialport.port)
        self.response_terminator = response_terminator
        super().__init__(verbose, daemon)
    
    def _send_message(self, message):
        if type(message) != bytes:
            message = bytes(message, encoding='ASCII')
        self.serialport.write(message)
    
    def _receive_message(self):
        tl = len(self.response_terminator)
        response = bytearray()
        while self.running: 
            response += self.serialport.read(max(1, self.serialport.inWaiting()))
            if len(response) >= tl and response[-tl:] == self.response_terminator:
                return str(response[:-tl], encoding='ASCII')

class EchoMessageManager(SerialMessageManager):
    """MessageManager subclass for debugging: the response key is the whole response"""
    def _generate_response_key(self, response):
        return response

class LeicaMessageManager(SerialMessageManager):
    """MessageManager subclass appropriate for routing messages from Leica API"""
    def __init__(self, serialport, verbose=False, daemon=True):
        super().__init__(serialport, response_terminator=b'\r', verbose=verbose, daemon=daemon)
        
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
            if self.verbose and response_key not in ('83023',):
                # Unexpected notifications are quite common, and if the dm6000b has communicated with MicroManager or the Leica
                # Windows software since last power cycled, they may be overwhelming in number.  Therefore, these are appropriately
                # confined to verbose mode.
                print('received UNEXPECTED notification from Leica device: {} with response key: {}'.format(response, response_key))
        else:
            # Unprompted command responses are an ominous sign and are of interest even if not in verbose mode
            print('received UNPROMPTED COMMAND RESPONSE from Leica device: {} with response key: {}'.format(response, response_key))
