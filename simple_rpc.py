import zmq
import traceback
import inspect
import collections

class Namespace:
    """Placeholder class to hold attribute values"""
    pass

class RPCServer:
    """Dispatch remote calls to callable objects in a local namespace.
    
    Calls take the form of command names with a separate arg list and kwarg dict.
    Command names are of the form 'foo.bar.baz', which will be looked up as:
    namespace.foo.bar.baz
    where 'namespace' is the top-level namespace provided to the server on initialization.
    Results from the calls are returned.
    
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
    def __init__(self, namespace, verbose=False):
        self.namespace = namespace
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
            self._reply(error='No such command: {}'.format(command))
            return
        try:
            response = py_command(*args, **kwargs)
            if self.verbose:
                print("\t response: {}".format(response))
            
        except Exception as e:
            exception_str = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
            self._reply(error=exception_str)
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

    def _reply(self, reply=None, error=None):
        """Reply to clients with either a valid response or an error string."""
        raise NotImplementedError()

    def _receive(self):
        """Block until an RPC call is received from the client, then return the call
        as (command_name, args, kwargs)."""
        raise NotImplementedError()

class ZMQServer(RPCServer):
    def __init__(self, namespace, port, context=None, verbose=False):
        """RPCServer subclass that uses ZeroMQ REQ/REP to communicate with clients.
        Arguments:
            namespace: contains a hierarchy of callable objects to expose to clients.
            port: a string ZeroMQ port identifier, like ''tcp://127.0.0.1:5555''.
            context: a ZeroMQ context to share, if one already exists.
        """
        super().__init__(namespace, verbose)
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
    
    def _reply(self, reply=None, error=None):
        response = {'retval':reply, 'error':error}
        try:
            json = zmq.utils.jsonapi.dumps(response)
        except:
            response = {'retval':None, 'error':'Could not JSON-serialize return value.'}
            json = zmq.utils.jsonapi.dumps(response)
        self.socket.send(json)


class RPCError(RuntimeError):
    pass

class RPCClient:
    """Client for simple remote procedure calls. RPC calls can be dispatched
    in three ways, given a client object 'client', and the desire to call 
    the server-side function foo.bar.baz(x, y, z=5):
    (1) client('foo.bar.baz', x, y, z=5)
    (2) foobarbaz = client.proxy_function('foo.bar.baz')
        foobarbaz(x, y, z=5)
    (3) namespace = client.proxy_namespace()
        namespace.foo.bar.baz(x, y, z=5)
        
    The last option provides much richer proxy functions complete with docstrings
    and appropriate argument names, defaults, etc., for run-time introspection. 
    In contrast, client.proxy_function() merely returns a simplistic function that
    takes *args and **kwargs parameters.
    """
    def __call__(self, command, *args, **kwargs):
        retval, error = self._send(command, args, kwargs)
        if error is not None:
            raise RPCError(error)
        return retval

    def _send(self, command, args, kwargs):
        raise NotImplementedError()

    def proxy_function(self, command):
        """Return a proxy function for server-side command 'command'."""
        def func(*args, **kwargs):
            return self.__call__(command, *args, **kwargs)
        func.__name__ = func.__qualname__ = command
        return func
    
    def proxy_namespace(self):
        """Use the RPC server's __DESCRIBE__ functionality to reconstitute a
        faxscimile namespace on the client side with well-described functions
        that can be seamlessly called."""
        # group functions by their namespace
        namespaces = collections.defaultdict(list)
        for qualname, doc, argspec in self('__DESCRIBE__'):
            *path, name = qualname.split('.')
            namespaces[tuple(path)].append((name, qualname, doc, argspec))
        
        # for each namespace that contains functions:
        # 1: see if there are any get/set pairs to turn into properties, and
        # 2: make a class for that namespace with the given properties and functions
        proxy_namespaces = {}
        for path, function_descriptions in namespaces.items():
            accessors = collections.defaultdict(RPCClient._accessor_pair)
            functions = {}
            for name, qualname, doc, argspec in function_descriptions:
                rpc_func = self.proxy_function(qualname)
                proxy_func = _rich_proxy_function(doc, argspec, name, rpc_func)
                functions[name] = proxy_func
                if name.startswith('get_'):
                    accessors[name[4:]].getter = proxy_func
                elif name.startswith('set_'):
                    accessors[name[4:]].setter = proxy_func
            # make a custom class to have the right names and more importantly to receive the namespace-specific properties
            class LocalNamespace(Namespace):
                pass
            LocalNamespace.__name__ = path[-1]
            LocalNamespace.__qualname__ = '.'.join(path)
            for name, accessor_pair in accessors.items():
                setattr(LocalNamespace, name, accessor_pair.get_property())
            for name, proxy_func in functions.items():
                setattr(LocalNamespace, name, proxy_func)
            local_namespace = LocalNamespace()
            proxy_namespaces[path] = local_namespace
        
        # now assemble these namespaces into the correct hierarchy, adding intermediate
        # namespaces as required
        root = proxy_namespaces.pop((), Namespace())
        for path in sorted(proxy_namespaces.keys(), key=len):
            # paths are sorted from less-deep to more-deep, so if the path isn't already in root, 
            # we know we need to make a new Namespace() to hold it. If we didn't sort, we might
            # get foo.bar from the proxy_namespaces dict first, and then get foo later, but we
            # would have already made a new Namespace() foo to hold bar at that point.
            *parent_path, name = path
            parent_namespace = self._namespace_lookup_or_create(root, parent_path)
            setattr(parent_namespace, name, proxy_namespaces[path])
        return root
    
    @staticmethod
    def _namespace_lookup_or_create(namespace, path_elements):
        """Find names nested in a namespace; if any elements of the name
        are not present, create a dummy Namespace object with that name.

        Example:
        namespace = Namespace()
        _namespace_lookup_or_create(namespace, ['foo', 'bar'])
        namespace.foo.bar.baz = 6
        _namespace_lookup_or_create(namespace, ['foo', 'quux'])
        namespace.foo.quux.baz = 5    
        """
        for element in path_elements:
            try:
                namespace = getattr(namespace, element)
            except AttributeError:
                new_namespace = Namespace()
                setattr(namespace, element, new_namespace)
                namespace = new_namespace
        return namespace
            
    class _accessor_pair:
        def __init__(self):
            self.getter = None
            self.setter = None

        def get_property(self):
            # assume one of self.getter or self.setter is set
            return property(self.getter, self.setter, doc=self.getter.__doc__ if self.getter else self.setter.__doc__)
        
        

class ZMQClient(RPCClient):
    def __init__(self, port, context=None):
        """RPCClient subclass that uses ZeroMQ REQ/REP to communicate with clients.
        Arguments:
            port: a string ZeroMQ port identifier, like ''tcp://127.0.0.1:5555''.
            context: a ZeroMQ context to share, if one already exists.
        """
        self._context = context if context is not None else zmq.Context()
        self._socket = self._context.socket(zmq.REQ)
        self._socket.connect(port)

    def _send(self, command, args, kwargs):
        self._socket.send_json((command, args, kwargs))
        reply_dict = self._socket.recv_json()
        return reply_dict['retval'], reply_dict['error']


def _rich_proxy_function(doc, argspec, name, to_proxy):
    """Using the docstring and argspec from the RPC __DESCRIBE__ command,
    generate a proxy function that looks just like the remote function, except
    wraps the function 'to_proxy' that is passed in."""
    args = argspec['args']
    defaults = argspec['defaults']
    varargs = argspec['varargs']
    varkw = argspec['varkw']
    kwonly = argspec['kwonlyargs']
    kwdefaults = argspec['kwonlydefaults']
    # note that the function we make has a "self" parameter as it is destined
    # to be added to a class and used as a method.
    arg_parts = ['self']
    call_parts = []
    # create the function by building up a python definition for that function
    # and exec-ing it.
    for arg in args:
        if arg in defaults:
            arg_parts.append('{}={}'.format(arg, defaults[arg]))
        else:
            arg_parts.append(arg)
        call_parts.append(arg)
    if varargs:
        call_parts.append('*{}'.format(varargs))
        arg_parts.append('*{}'.format(varargs))
    if varkw:
        call_parts.append('**{}'.format(varkw))
        arg_parts.append('**{}'.format(varkw))
    if kwonly:
        if not varargs:
            arg_parts.append('*')
        for arg in kwonly:
            call_parts.append('{}={}'.format(arg, arg))
            if arg in kwdefaults:
                arg_parts.append('{}={}'.format(arg, kwdefaults[arg]))
            else:
                arg_parts.append(arg)
    # we actually create a factory-function via exec, which then when called
    # creates the real function. This is necessary to generate the real proxy
    # function with 'to_proxy' stored inside a closure, as exec() doesn't know
    # to generate closures correctly.
    func_str = '''
        def make_func(to_proxy):
            def {}({}):
                """{}"""
                return to_proxy({})
            return {}
    '''.format(name, ', '.join(arg_parts), doc, ', '.join(call_parts), name)
    fake_locals = {} # dict in which exec operates: locals() doesn't work here.
    exec(func_str.strip(), globals(), fake_locals)
    func = fake_locals['make_func'](to_proxy) # call the factory function
    func.__qualname__ = func.__name__ = name # rename the proxy function
    return func


if __name__ == '__main__':
    import sys
    import argparse
    h = '  Note that the default values for first_serial_device '
    h+= 'and second_serial_device are appropriate for OSX but not Linux.'
    argparser = argparse.ArgumentParser(description='ZMQ RPC echo test client/server.', epilog=h)
    argparser.add_argument('--mode', choices=('client', 'server'), required=True)
    argparser.add_argument('--first-serial-device', metavar='first_serial_device', default='/dev/ptyp1')
    argparser.add_argument('--second-serial-device', metavar='second_serial_device', default='/dev/ttyp1')
    args = argparser.parse_args()

    if args.mode == 'client':
        c  = ZMQClient('tcp://localhost:5555')
        root = c.proxy_namespace()
        root.am.send_message('foo\n', async=True)
        root.am.send_message('bar\n', async=True)
        root.wait()
    
    elif args.mode == 'server':
        import subprocess
        import serial
        import message_manager
        import message_device
        import time
        import atexit
        
        p = subprocess.Popen([sys.executable, 'echo_device.py', args.first_serial_device])
        atexit.register(p.kill)
        time.sleep(0.2)
        s = serial.Serial(args.second_serial_device, timeout=10)
        sm = message_manager.EchoMessageManager(s, b'\n')
        am = message_device.EchoAsyncDevice(sm)
        root = message_device.AsyncDeviceNamespace()
        root.am = am
        zs = ZMQServer(root, 'tcp://127.0.0.1:5555')
        zs.run()
        

        