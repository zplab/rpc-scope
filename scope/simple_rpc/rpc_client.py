# This code is licensed under the MIT License (see LICENSE file for details)

import zmq
import collections
import contextlib
import time

from zplib import datafile

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
        self._send(command, args, kwargs)
        try:
            retval, is_error = self._receive_reply()
        except KeyboardInterrupt:
            self.send_interrupt()
            retval, is_error = self._receive_reply()
        if is_error:
            raise RPCError(retval)
        return retval

    def _send(self, command, args, kwargs):
        raise NotImplementedError()

    def _receive_reply(self):
        raise NotImplementedError()

    def send_interrupt(self):
        """Raise a KeyboardInterrupt exception in the server process"""
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
        that can be seamlessly called.

        A set of the fully-qualified function names available in the namespace
        is included as the _functions_proxied attribute of this namespace.
        """
        # group functions by their namespace
        server_namespaces = collections.defaultdict(list)
        functions_proxied = set()
        for qualname, doc, argspec in self('__DESCRIBE__'):
            functions_proxied.add(qualname)
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
            class NewNamespace(_ClientNamespace):
                pass
            NewNamespace.__name__ = parents[-1] if parents else 'root'
            NewNamespace.__qualname__ = '.'.join(parents) if parents else 'root'
            # create functions and gather property accessors
            accessors = collections.defaultdict(_AccessorProperty)
            for name, qualname, doc, argspec in function_descriptions:
                client_func = _rich_proxy_function(doc, argspec, name, self, qualname)
                if name.startswith('get_'):
                    accessors[name[4:]].getter = client_func
                    name = '_'+name
                elif name.startswith('set_'):
                    accessors[name[4:]].setter = client_func
                    name = '_'+name
                setattr(NewNamespace, name, client_func)
            for name, accessor_property in accessors.items():
                accessor_property._set_doc()
                setattr(NewNamespace, name, accessor_property)
            client_namespaces[parents] = NewNamespace()

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
        root._functions_proxied = functions_proxied
        return root


class _AccessorProperty:
    def __init__(self):
        self.getter = None
        self.setter = None

    def _set_doc(self):
        assert self.getter or self.setter # at least one must not be None!
        self.__doc__ = self.getter.__doc__ if self.getter else self.setter.__doc__

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        if self.getter is None:
            raise AttributeError('unreadable attribute')
        return self.getter()

    def __set__(self, obj, value):
        if self.setter is None:
            raise AttributeError("can't set attribute")
        self.setter(value)


class _ClientNamespace:
    __attrs_locked = False

    def _lock_attrs(self):
        self.__attrs_locked = True
        for v in self.__dict__.values():
            if hasattr(v, '_lock_attrs'):
                v._lock_attrs()

    def __setattr__(self, name, value):
        if self.__attrs_locked:
            if not hasattr(self, name):
                raise RPCError('Attribute "{}" is not known, so its state cannot be communicated to the server.'.format(name))
            else:
                cls = type(self)
                if not hasattr(cls, name) or not isinstance(getattr(cls, name), _AccessorProperty):
                    raise RPCError('Attribute "{}" is not a property value that can be communicated to the server.'.format(name))
        super().__setattr__(name, value)


class ZMQClient(RPCClient):
    def __init__(self, rpc_addr, interrupt_addr=None, heartbeat_sec=None, timeout_sec=10, context=None):
        """RPCClient subclass that uses ZeroMQ REQ/REP to communicate.
        Parameters:
            rpc_addr: a string ZeroMQ port identifier, like 'tcp://127.0.0.1:5555'.
            timeout_sec: timeout in seconds for RPC call to fail.
            context: a ZeroMQ context to share, if one already exists.
        """
        self.context = context if context is not None else zmq.Context()
        self.rpc_addr = rpc_addr
        self.interrupt_addr = interrupt_addr
        self.heartbeat_sec = heartbeat_sec
        self._timeout_sec = timeout_sec
        self._connect()

    def _connect(self):
        self.socket = self.context.socket(zmq.REQ)
        self.socket.RCVTIMEO = 0 # we use poll to determine when a message is ready, so set a zero timeout
        self.socket.LINGER = 0
        self.socket.REQ_RELAXED = True
        self.socket.REQ_CORRELATE = True
        if self.heartbeat_sec is not None:
            heartbeat_ms = self.heartbeat_sec * 1000
            self.socket.HEARTBEAT_IVL = heartbeat_ms
            self.socket.HEARTBEAT_TIMEOUT = heartbeat_ms * 2
            self.socket.HEARTBEAT_TTL = heartbeat_ms * 2
        self.socket.connect(self.rpc_addr)

        if self.interrupt_addr is not None:
            self.interrupt_socket = self.context.socket(zmq.PUSH)
            self.interrupt_socket.LINGER = 0
            if self.heartbeat_sec is not None:
                self.interrupt_socket.HEARTBEAT_IVL = heartbeat_ms
                self.interrupt_socket.HEARTBEAT_TIMEOUT = heartbeat_ms * 2
                self.interrupt_socket.HEARTBEAT_TTL = heartbeat_ms * 2
            self.interrupt_socket.connect(self.interrupt_addr)

    def reconnect(self):
        self.socket.close()
        if self.interrupt_addr is not None:
            self.interrupt_socket.close()
        self._connect()

    @contextlib.contextmanager
    def timeout_sec(self, timeout_sec):
        """Context manager to alter the timeout time."""
        old_timeout = self._timeout_sec
        if timeout_sec is not None:
            self._timeout_sec = timeout_sec
        try:
            yield
        finally:
            self._timeout_sec = old_timeout

    def _send(self, command, args, kwargs):
        json = datafile.json_encode_compact_to_bytes((command, args, kwargs))
        self.socket.send(json)

    def _receive_reply(self):
        if not self.socket.poll(self._timeout_sec * 1000):
            raise RPCError('Timed out waiting for reply from server (is it running?)')
        while True:
            try:
                reply_type = self.socket.recv_string()
                break
            except zmq.Again:
                time.sleep(0.001)
        assert(self.socket.RCVMORE)
        if reply_type == 'bindata':
            reply = self.socket.recv(copy=False, track=False).buffer
        else:
            reply = self.socket.recv_json()
        return reply, reply_type == 'error'

    def send_interrupt(self):
        """Raise a KeyboardInterrupt exception in the server process"""
        if self.interrupt_addr is not None:
            self.interrupt_socket.send(b'interrupt')


class _ProxyMethodClass:
    def __init__(self, rpc_client, rpc_function):
        self._rpc_client = rpc_client
        self._rpc_function = rpc_function
        self._timeout_sec = None
        self._output_handler = lambda x: x # no-op handler

    def _call_function(self, *args, **kws):
        with self._rpc_client.timeout_sec(self._timeout_sec):
            result = self._rpc_client(self._rpc_function, *args, **kws)
        return self._output_handler(result)


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
    arg_parts = []
    call_parts = []
    # create the function by building up a python definition for that function
    # and exec-ing it.
    for arg in args:
        if arg in defaults:
            arg_parts.append(f'{arg}={defaults[arg]!r}')
        else:
            arg_parts.append(arg)
        call_parts.append(arg)
    if varargs:
        fstr = f'*{varargs}'
        call_parts.append(fstr)
        arg_parts.append(fstr)
    if varkw:
        fstr = f'**{varkw}'
        call_parts.append(fstr)
        arg_parts.append(fstr)
    if kwonly:
        if not varargs:
            arg_parts.append('*')
        for arg in kwonly:
            call_parts.append(f'{arg}={arg}')
            if arg in kwdefaults:
                arg_parts.append(f'{arg}={kwdefaults[arg]!r}')
            else:
                arg_parts.append(arg)
    arg_parts = ', '.join(arg_parts)
    call_parts = ', '.join(call_parts)
    class_def = f"""
        class {name}(_ProxyMethodClass):
            def __call__(self, {arg_parts}):
                '''{doc}'''
                return self._call_function({call_parts})"""
    namespace = {} # dict in which exec operates
    exec(class_def.strip(), globals(), namespace)
    ProxyClass = namespace[name]
    # now pretend that the given class was defined in a module named like the rpc function's namespace
    ProxyClass.__module__ = rpc_function.rsplit('.', maxsplit=1)[0]
    return ProxyClass(rpc_client, rpc_function)
