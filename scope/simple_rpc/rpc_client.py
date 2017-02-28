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
# Authors: Zach Pincus

import zmq
import collections
import contextlib
import time

from zplib import util

from . import heartbeat

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
            self._send_interrupt()
            retval, is_error = self._receive_reply()
        if is_error:
            raise RPCError(retval)
        return retval

    def _send(self, command, args, kwargs):
        raise NotImplementedError()

    def _receive_reply(self):
        raise NotImplementedError()

    def _send_interrupt(self):
        raise NotImplementedError()

    def proxy_function(self, command):
        """Return a proxy function for server-side command 'command'."""
        def func(*args, **kwargs):
            return self.__call__(command, *args, **kwargs)
        func.__name__ = func.__qualname__ = command
        return func

    def proxy_namespace(self, client_wrappers=None):
        """Use the RPC server's __DESCRIBE__ functionality to reconstitute a
        faxscimile namespace on the client side with well-described functions
        that can be seamlessly called.

        A set of the fully-qualified function names available in the namespace
        is included as the _functions_proxied attribute of this namespace.

        If client_wrappers is provided, it must be a dict mapping qualified
        function names to functions that will be used to wrap that RPC call. For
        example, if certain data returned from the RPC server needs additional
        processing before returning to the client, this can be used for that
        purpose.
        """
        if client_wrappers is None:
            client_wrappers = {}
        # group functions by their namespace
        server_namespaces = collections.defaultdict(list)
        functions_proxied = set()
        for qualname, doc, argspec in  self('__DESCRIBE__'):
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
            class NewNamespace(ClientNamespace):
                pass
            NewNamespace.__name__ = parents[-1] if parents else 'root'
            NewNamespace.__qualname__ = '.'.join(parents) if parents else 'root'
            # create functions and gather property accessors
            accessors = collections.defaultdict(RPCClient._accessor_pair)
            for name, qualname, doc, argspec in function_descriptions:
                client_wrap_function = client_wrappers.pop(qualname, None)
                client_func = _rich_proxy_function(doc, argspec, name, self, qualname, client_wrap_function)
                if name.startswith('get_'):
                    accessors[name[4:]].getter = client_func
                    name = '_'+name
                elif name.startswith('set_'):
                    accessors[name[4:]].setter = client_func
                    name = '_'+name
                setattr(NewNamespace, name, client_func)
            for name, accessor_pair in accessors.items():
                setattr(NewNamespace, name, accessor_pair.get_property())
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

    class _accessor_pair:
        def __init__(self):
            self.getter = None
            self.setter = None

        def get_property(self):
            # assume one of self.getter or self.setter is set
            return property(self.getter, self.setter, doc=self.getter.__doc__ if self.getter else self.setter.__doc__)

class ClientNamespace:
    __attrs_locked = False
    def _lock_attrs(self):
        self.__attrs_locked = True
        for v in self.__dict__.values():
            if hasattr(v, '_lock_attrs'):
                v._lock_attrs()
    def __setattr__(self, name, value):
        if self.__attrs_locked:
            if not hasattr(self, name):
                raise RuntimeError('Attribute "{}" is not known, so its state cannot be communicated to the server.'.format(name))
            else:
                cls = type(self)
                if not hasattr(cls, name) or not isinstance(getattr(cls, name), property):
                    raise RuntimeError('Attribute "{}" is not a property value that can be communicated to the server.'.format(name))
        super().__setattr__(name, value)

class RPCError(RuntimeError):
    pass

class ZMQClient(RPCClient):
    def __init__(self, rpc_addr, timeout_sec=None, context=None):
        """RPCClient subclass that uses ZeroMQ REQ/REP to communicate.
        Parameters:
            rpc_addr: a string ZeroMQ port identifier, like 'tcp://127.0.0.1:5555'.
            timeout_sec: timeout in seconds for RPC call to fail.
            context: a ZeroMQ context to share, if one already exists.
        """
        self.context = context if context is not None else zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        # main timeout will be implemented with poll
        self.timeout_sec = timeout_sec
        self.socket.RCVTIMEO = 1000 # timeout receive after 1 sec, in case server dies after poll succeeds
        self.socket.LINGER = 0
        self.heartbeat_client = None
        self.interrupt_socket = None
        self.heartbeat_error = False
        self.socket.connect(rpc_addr)

    def enable_interrupt(self, interrupt_addr):
        self.interrupt_socket = self.context.socket(zmq.PUSH)
        self.interrupt_socket.connect(interrupt_addr)

    def enable_heartbeat(self, heartbeat_addr, heartbeat_interval_sec):
        self.heartbeat_client = heartbeat.ZMQClient(heartbeat_addr, heartbeat_interval_sec,
            max_missed=3, error_callback=self._set_heartbeat_error, context=self.context)

    def _set_heartbeat_error(self):
        self.heartbeat_error = True

    def _send(self, command, args, kwargs):
        json = util.json_encode_compact_to_bytes((command, args, kwargs))
        self.socket.send(json)

    def _receive_reply(self):
        timeout_time = time.time() + self.timeout_sec
        timeout_errtext = 'Timed out waiting for reply from server (is it running?)'
        while True:
            if time.time() > timeout_time:
                self._send_interrupt()
                self._timeout_recv()
                raise RuntimeError(timeout_errtext)
            if self.heartbeat_error:
                self._send_interrupt()
                self._timeout_recv()
                raise RuntimeError('No "heartbeat" signal detected from server (is it still running?)')
            if self.socket.poll(500): # 500 ms timeout
                break
        try:
            reply_type = self.socket.recv_string()
            assert(self.socket.RCVMORE)
            if reply_type == 'bindata':
                reply = self.socket.recv(copy=False, track=False).buffer
            else:
                reply = self.socket.recv_json()
            return reply, reply_type == 'error'
        except zmq.error.Again:
            raise RuntimeError(timeout_errtext)

    def _send_interrupt(self):
        if self.interrupt_socket is not None:
            self.interrupt_socket.send(b'interrupt')

    def _timeout_recv(self):
        timeout = self.socket.RCVTIMEO
        self.socket.RCVTIMEO = 0
        try:
            self.socket.recv()
        except zmq.error.Again:
            pass
        finally:
            self.socket.RCVTIMEO = timeout

def _rich_proxy_function(doc, argspec, name, rpc_client, rpc_function, client_wrap_function=None):
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
            arg_parts.append('{}={!r}'.format(arg, defaults[arg]))
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
                arg_parts.append('{}={!r}'.format(arg, kwdefaults[arg]))
            else:
                arg_parts.append(arg)
    # we actually create a factory-function via exec, which when called
    # creates the real function. This is necessary to generate the real proxy
    # function with the function to proxy stored inside a closure, as exec()
    # can't generate closures correctly.
    rpc_call = 'rpc_client(rpc_function, {})'.format(', '.join(call_parts))
    if client_wrap_function is not None:
        rpc_call = 'client_wrap_function({})'.format(rpc_call)
    func_str = """
        def make_func(rpc_client, rpc_function, client_wrap_function):
            def {}({}):
                '''{}'''
                return {}
            return {}
    """.format(name, ', '.join(arg_parts), doc, rpc_call, name)
    fake_locals = {} # dict in which exec operates: locals() doesn't work here.
    exec(func_str.strip(), globals(), fake_locals)
    func = fake_locals['make_func'](rpc_client, rpc_function, client_wrap_function) # call the factory function
    func.__qualname__ = func.__name__ = name # rename the proxy function
    return func