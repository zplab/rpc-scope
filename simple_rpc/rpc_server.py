import zmq
import traceback
import inspect
import threading
import os
import signal

class RPCServer:
    """Dispatch remote calls to callable objects in a local namespace.
    
    Calls take the form of command names with a separate arg list and kwarg dict.
    Command names are of the form 'foo.bar.baz', which will be looked up as:
    namespace.foo.bar.baz
    where 'namespace' is the top-level namespace provided to the server on initialization.
    Results from the calls are returned.
    
    The 'interrupter' parameter must be an instance of Interrupter, which can be used
    to simulate control-c interrupts during RPC calls.
    
    Introspection can be used to provide clients a description of available commands.
    The special '__DESCRIBE__' command returns a list of command descriptions,
    which are triples of (command_name, command_doc, arg_info):
        command_name is the fully-qualified path to the command within 'namespace'.
        command_doc is the function's docstring.
        arg_info is a dict containing the following keys:
            args: list of argument names
            defaults: dict mapping argument names to default values (if any)
            varargs: name of the variable-arglist parameter (usually '*args', but without the asterisk)
            varkw: name of the variable-keyword parameter (usually '**kwarg', but without the asterisks)
            kwonlyargs: list of keyword-only arguments
            kwonlydefaults: dict mapping keyword-only argument names to default values (if any)
    """
    def __init__(self, namespace, interrupter, verbose=False):
        self.namespace = namespace
        self.interrupter = interrupter
        self.verbose = verbose

    def run(self):
        """Run the RPC server. To quit the server from another thread,
        set the 'running' attribute to False."""
        self.running = True
        while self.running:
            command, args, kwargs = self._receive()
            if self.verbose:
                print("Received command: {}".format(command))
                print("\t args: {}".format(args))
                print("\t kwargs: {}".format(kwargs))
            self.process_command(command, args, kwargs)
        
    def process_command(self, command, args, kwargs):
        """Dispatch a command or deal with special keyword commands.
        Currently, only __DESCRIBE__ is supported. 
        """
        if command == '__DESCRIBE__':
            self.describe()
        else:
            self.call(command, args, kwargs)
    
    def describe(self):
        descriptions = []
        self.gather_descriptions(descriptions, self.namespace)
        self._reply(descriptions)
    
    @staticmethod
    def gather_descriptions(descriptions, namespace, prefix=''):
        """Recurse through a namespace, adding descriptions of callable objects encountered
        to the 'descriptions' list."""
        for k in dir(namespace):
            if k.startswith('_'):
                continue
            prefixed_name = '.'.join((prefix, k)) if prefix else k
            v = getattr(namespace, k)
            if callable(v) and not inspect.isclass(v):
                try:
                    doc = v.__doc__
                    if doc is None:
                        doc = ''
                except AttributeError:
                    doc = ''
                argspec = inspect.getfullargspec(v)
                argdict = argspec.__dict__
                argdict.pop('annotations')
                if argdict['defaults']:
                    defaults = dict(zip(reversed(argdict['args']), reversed(argdict['defaults']))) 
                else:
                    defaults = {}
                argdict['defaults'] = defaults
                if inspect.ismethod(v):
                    argdict['args'] = argdict['args'][1:] # remove 'self'
                descriptions.append((prefixed_name, doc, argdict))
            else:
                try:
                    subnamespace = v
                except AttributeError:
                    continue
                RPCServer.gather_descriptions(descriptions, subnamespace, prefixed_name)
    
    def call(self, command, args, kwargs):
        """Call the named command with *args and **kwargs"""
        py_command = self.lookup(command)
        if py_command is None:
            self._reply('No such command: {}'.format(command), error=True)
            return
        try:
            self.interrupter.armed = True
            response = py_command(*args, **kwargs)
            self.interrupter.armed = False
            if self.verbose:
                print("\t response: {}".format(response))
            
        except (Exception, KeyboardInterrupt) as e:
            exception_str = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
            self._reply(exception_str, error=True)
        else:
            self._reply(response)
    
    def lookup(self, name):
        """Look up a name in the namespace, allowing for multiple levels e.g. foo.bar.baz"""
        # could just eval, but since command is coming from the network, that's a bad idea.
        v = self.namespace
        for k in name.split('.'):
            try:
                v = getattr(v, k)
            except AttributeError:
                return None
        return v

    def _reply(self, reply, error=False):
        """Reply to clients with either a valid response or an error string."""
        raise NotImplementedError()

    def _receive(self):
        """Block until an RPC call is received from the client, then return the call
        as (command_name, args, kwargs)."""
        raise NotImplementedError()

class ZMQServer(RPCServer):
    def __init__(self, namespace, interrupter, port, context=None, verbose=False):
        """RPCServer subclass that uses ZeroMQ REQ/REP to communicate with clients.
        Arguments:
            namespace: contains a hierarchy of callable objects to expose to clients.
            interrupter: Interrupter instance for simulating control-c on server
            port: a string ZeroMQ port identifier, like 'tcp://127.0.0.1:5555'.
            context: a ZeroMQ context to share, if one already exists.
        """
        super().__init__(namespace, interrupter, verbose)
        self.context = context if context is not None else zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        self.socket.bind(port)

    def _receive(self):
        json = self.socket.recv()
        try:
            command, args, kwargs = zmq.utils.jsonapi.loads(json)
        except:
            self._reply(error='Could not unpack command, arguments, and keyword arguments from JSON message.')
        return command, args, kwargs
    
    def _reply(self, reply, error=False):
        if error:
            reply_type = 'error'
        elif isinstance(reply, bytes):
            reply_type = 'bindata'
        else:
            reply_type = 'json'

        if reply_type == 'error' or reply_type == 'json':
            try:
                reply = zmq.utils.jsonapi.dumps(reply)
            except TypeError:
                reply_type = 'error'
                reply = zmq.utils.jsonapi.dumps('Could not JSON-serialize return value.')
        self.socket.send_string(reply_type, flags=zmq.SNDMORE)
        self.socket.send(reply, copy=False)

class Namespace:
    """Placeholder class to hold attribute values"""
    pass

class Interrupter(threading.Thread):
    """Interrupter runs in a background thread and creates KeyboardInterrupt
    events in the main thread when requested to do so."""
    def __init__(self, verbose=False):
        super().__init__(name='InterruptServer', daemon=True)
        self.running = True
        self.armed = False
        self.verbose = verbose
        self.start()
    
    def run(self):
        while self.running:
            message = self._receive()
            if self.verbose:
                print('interrupt received: {}, armed={}'.format(message, self.armed))
            if message == 'interrupt' and self.armed:
                os.kill(os.getpid(), signal.SIGINT)

    def _receive(self):
        raise NotImplementedError()
        

class ZMQInterrupter(Interrupter):
    def __init__(self, port, context=None, verbose=False):
        """InterruptServer subclass that uses ZeroMQ PUSH/PULL to communicate with clients.
        Arguments:
            port: a string ZeroMQ port identifier, like ''tcp://127.0.0.1:5555''.
            context: a ZeroMQ context to share, if one already exists.
        """
        self.context = context if context is not None else zmq.Context()
        self.socket = self.context.socket(zmq.PULL)
        self.socket.bind(port)
        super().__init__(verbose)
    
    def _receive(self):
        return str(self.socket.recv(), encoding='ascii')