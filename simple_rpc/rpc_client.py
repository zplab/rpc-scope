import zmq
import collections

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
        self._send(command, args, kwargs)
        try:
            retval, error = self._receive_reply()
        except KeyboardInterrupt:
            self._send_interrupt('interrupt')
            retval, error = self._receive_reply()
        if error is not None:
            raise RPCError(error)
        return retval

    def _send(self, command, args, kwargs):
        raise NotImplementedError()
    
    def _receive_reply(self):
        raise NotImplementedError()
    
    def _send_interrupt(self, message):
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
        server_namespaces = collections.defaultdict(list)
        for qualname, doc, argspec in self('__DESCRIBE__'):
            *parents, name = qualname.split('.')
            parents = tuple(parents)
            server_namespaces[parents].append((name, qualname, doc, argspec))
            # make sure that intermediate (and possibly-empty) namespaces are also in the dict
            for i in range(len(parents)):
                server_namespaces[parents[:i]] # for a defaultdict, just looking up the entry adds it
        
        # for each namespace that contains functions:
        # 1: see if there are any get/set pairs to turn into properties, and
        # 2: make a class for that namespace with the given properties and functions
        client_namespaces = {}
        for parents, function_descriptions in server_namespaces.items():
            # make a custom class to have the right names and more importantly to receive the namespace-specific properties
            class ClientNamespace:
                pass
            ClientNamespace.__name__ = parents[-1] if parents else 'root'
            ClientNamespace.__qualname__ = '.'.join(parents) if parents else 'root'
            # create functions and gather property accessors
            accessors = collections.defaultdict(RPCClient._accessor_pair)
            for name, qualname, doc, argspec in function_descriptions:
                client_func = _rich_proxy_function(doc, argspec, name, self, qualname)
                if name.startswith('get_'):
                    accessors[name[4:]].getter = client_func
                    name = '_'+name
                elif name.startswith('set_'):
                    accessors[name[4:]].setter = client_func
                    name = '_'+name
                setattr(ClientNamespace, name, client_func)
            for name, accessor_pair in accessors.items():
                setattr(ClientNamespace, name, accessor_pair.get_property())
            client_namespaces[parents] = ClientNamespace()

        
        # now assemble these namespaces into the correct hierarchy, fetching intermediate
        # namespaces from the proxy_namespaces dict as required.
        root = client_namespaces[()]
        for parents in list(client_namespaces.keys()):
            if parents not in client_namespaces:
                # we might have already popped it below
                continue
            namespace = root
            for i, element in enumerate(parents):
                try:
                    namespace = getattr(namespace, element)
                except AttributeError:
                    new_namespace = client_namespaces.pop(parents[:i+1])
                    setattr(namespace, element, new_namespace)
                    namespace = new_namespace            
        return root
                
    class _accessor_pair:
        def __init__(self):
            self.getter = None
            self.setter = None

        def get_property(self):
            # assume one of self.getter or self.setter is set
            return property(self.getter, self.setter, doc=self.getter.__doc__ if self.getter else self.setter.__doc__)

class RPCError(RuntimeError):
    pass

class ZMQClient(RPCClient):
    def __init__(self, rpc_port, interrupt_port, context=None):
        """RPCClient subclass that uses ZeroMQ REQ/REP to communicate.
        Arguments:
            rpc_port, interrupt_port: a string ZeroMQ port identifier, like ''tcp://127.0.0.1:5555''.
            context: a ZeroMQ context to share, if one already exists.
        """
        self.context = context if context is not None else zmq.Context()
        self.rpc_socket = self.context.socket(zmq.REQ)
        self.rpc_socket.connect(rpc_port)
        self.interrupt_socket = self.context.socket(zmq.PUSH)
        self.interrupt_socket.connect(interrupt_port)

    def _send(self, command, args, kwargs):
        self.rpc_socket.send_json((command, args, kwargs))
    
    def _receive_reply(self):
        reply_dict = self.rpc_socket.recv_json()
        return reply_dict['retval'], reply_dict['error']

    def _send_interrupt(self, message):
        self.interrupt_socket.send(bytes(message, encoding='ascii'))

def _rich_proxy_function(doc, argspec, name, rpc_client, rpc_function):
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
        def make_func(rpc_client, rpc_function):
            def {}({}):
                """{}"""
                return rpc_client(rpc_function, {})
            return {}
    '''.format(name, ', '.join(arg_parts), doc, ', '.join(call_parts), name)
    fake_locals = {} # dict in which exec operates: locals() doesn't work here.
    exec(func_str.strip(), globals(), fake_locals)
    func = fake_locals['make_func'](rpc_client, rpc_function) # call the factory function
    func.__qualname__ = func.__name__ = name # rename the proxy function
    return func