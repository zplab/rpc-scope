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
            self._send_interrupt('interrupt')
            retval, is_error = self._receive_reply()
        if is_error:
            raise RPCError(retval)
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
            class ClientNamespace:
                pass
            ClientNamespace.__name__ = parents[-1] if parents else 'root'
            ClientNamespace.__qualname__ = '.'.join(parents) if parents else 'root'
            # create functions and gather property accessors
            accessors = collections.defaultdict(RPCClient._accessor_pair)
            for name, qualname, doc, argspec in function_descriptions:
                if qualname in client_wrappers:
                    client_wrap_function = client_wrappers[qualname]
                else:
                    client_wrap_function = None
                client_func = _rich_proxy_function(doc, argspec, name, self, qualname, client_wrap_function)
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
        root._functions_proxied = functions_proxied
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
    def __init__(self, rpc_addr, interrupt_addr, context=None):
        """RPCClient subclass that uses ZeroMQ REQ/REP to communicate.
        Parameters:
            rpc_addr, interrupt_addr: a string ZeroMQ port identifier, like ''tcp://127.0.0.1:5555''.
            context: a ZeroMQ context to share, if one already exists.
        """
        self.context = context if context is not None else zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect(rpc_addr)
        self.interrupt_socket = self.context.socket(zmq.PUSH)
        self.interrupt_socket.connect(interrupt_addr)

    def _send(self, command, args, kwargs):
        self.socket.send_json((command, args, kwargs))

    def _receive_reply(self):
        reply_type = self.socket.recv_string()
        assert(self.socket.getsockopt(zmq.RCVMORE))
        if reply_type == 'bindata':
            reply = self.socket.recv(copy=False, track=False).buffer
        else:
            reply = self.socket.recv_json()
        return reply, reply_type == 'error'

    def _send_interrupt(self, message):
        self.interrupt_socket.send(bytes(message, encoding='ascii'))

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