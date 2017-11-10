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
# PyZMQ 15.0.0's __init__.py apparently does not import utils, requiring this explicit import
import zmq.utils
# Likewise for zmq.utils.jsonapi
import zmq.utils.jsonapi
import traceback
import inspect
import threading
import os
import signal
import contextlib

from zplib import datafile

from ..util import logging
logger = logging.get_logger(__name__)

class BaseRPCServer:
    """Dispatch remote calls to callables specified in a potentially-nested namespace.
    """
    def __init__(self, namespace):
        self.namespace = namespace

    def run(self):
        """Run the RPC server. To quit the server from another thread,
        set the 'running' attribute to False."""
        self.running = True
        while self.running:
            received = self._receive()
            if received is not None:
                command, args, kwargs = received
                logger.debug("Received command: {}\n    args: {}\n    kwargs: {}", command, args, kwargs)
                self.call(command, args, kwargs)
            else:
                logger.debug("_receive() returned None!?")

    def call(self, command, args, kwargs):
        """Call the named command with *args and **kwargs"""
        py_command = self.lookup(command)
        if py_command is None:
            self._reply('No such command: {}'.format(command), error=True)
            logger.info('Received unknown command: {}', command)
            return
        try:
            response = self.run_command(py_command, args, kwargs)

        except (Exception, KeyboardInterrupt) as e:
            exception_str = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
            logger.debug('Exception caught: {}', exception_str)
            self._reply(exception_str, error=True)
        else:
            logger.debug('Sending response: {}', response)
            self._reply(response)

    def run_command(self, py_command, args, kwargs):
        return py_command(*args, **kwargs)

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

class ZMQServerMixin:
    def __init__(self, port, context=None):
        """Mixin for RPC servers that uses ZeroMQ REQ/REP to communicate with clients.
        Parameters:
            port: a string ZeroMQ port identifier, like 'tcp://127.0.0.1:5555'.
            context: a ZeroMQ context to share, if one already exists.
        """
        self.context = context if context is not None else zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        self.socket.bind(port)

    def run(self):
        try:
            super().run()
        finally:
            self.socket.close()

    def _receive(self):
        json = self.socket.recv()
        try:
            command, args, kwargs = zmq.utils.jsonapi.loads(json)
            return command, args, kwargs
        except Exception as e:
            self._reply('Could not unpack command, arguments, and keyword arguments from JSON message: {}'.format(e), error=True)

    def _reply(self, reply, error=False):
        if error:
            reply_type = 'error'
        elif isinstance(reply, (bytearray, bytes, memoryview)):
            reply_type = 'bindata'
        else:
            reply_type = 'json'

        if reply_type == 'error' or reply_type == 'json':
            try:
                reply = datafile.json_encode_compact_to_bytes(reply)
            except TypeError:
                reply_type = 'error'
                reply = datafile.json_encode_compact_to_bytes('Could not JSON-serialize return value.')
        self.socket.send_string(reply_type, flags=zmq.SNDMORE)
        self.socket.send(reply) # TODO: profile to see if copy=False improves performance


class BaseZMQServer(ZMQServerMixin, BaseRPCServer):
    def __init__(self, namespace, port, context=None):
        """BaseRPCServer subclass that uses ZeroMQ REQ/REP to communicate with clients.
        Parameters:
            namespace: contains a hierarchy of callable objects to expose to clients.
            port: a string ZeroMQ port identifier, like 'tcp://127.0.0.1:5555'.
            context: a ZeroMQ context to share, if one already exists.
        """
        BaseRPCServer.__init__(self, namespace)
        ZMQServerMixin.__init__(self, port, context)


class BackgroundBaseZMQServer(BaseZMQServer, threading.Thread):
    """ZMQ server that runs in a background thread."""
    def __init__(self, namespace, port, context=None):
        BaseZMQServer.__init__(self, namespace, port, context)
        threading.Thread.__init__(self, name='background RPC server', daemon=True)
        self.start()


class RPCServer(BaseRPCServer):
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
    def __init__(self, namespace, interrupter):
        super().__init__(namespace)
        self.interrupter = interrupter

    def call(self, command, args, kwargs):
        """Dispatch a command or deal with special keyword commands.
        Currently, only __DESCRIBE__ is supported.
        """
        if command == '__DESCRIBE__':
            descriptions = []
            self.gather_descriptions(descriptions, self.namespace)
            self._reply(descriptions)
        else:
            super().call(command, args, kwargs)

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
                try:
                    argspec = inspect.getfullargspec(v)
                except TypeError:
                    raise TypeError('Could not get description of callable "{}"'.format(prefixed_name))
                argdict = {}
                if argspec.defaults:
                    # if there are fewer defaults than args, the args at the end of the list get the defaults
                    has_default = argspec.args[-len(argspec.defaults):]
                    defaults = dict(zip(has_default, argspec.defaults))
                else:
                    defaults = {}
                argdict['defaults'] = defaults
                argdict['args'] = argspec.args[1:] if inspect.ismethod(v) else argspec.args # remove 'self'
                argdict['varargs'] = argspec.varargs
                argdict['varkw'] = argspec.varkw
                argdict['kwonlyargs'] = argspec.kwonlyargs
                argdict['kwonlydefaults'] = argspec.kwonlydefaults if argspec.kwonlydefaults else {}
                descriptions.append((prefixed_name, doc, argdict))
            else:
                try:
                    subnamespace = v
                except AttributeError:
                    continue
                RPCServer.gather_descriptions(descriptions, subnamespace, prefixed_name)

    def run_command(self, py_command, args, kwargs):
            with self.interrupter.armed():
                return py_command(*args, **kwargs)


class ZMQServer(ZMQServerMixin, RPCServer):
    def __init__(self, namespace, interrupter, port, context=None):
        """RPCServer subclass that uses ZeroMQ REQ/REP to communicate with clients.
        Parameters:
            namespace: contains a hierarchy of callable objects to expose to clients.
            interrupter: Interrupter instance for simulating control-c on server
            port: a string ZeroMQ port identifier, like 'tcp://127.0.0.1:5555'.
            context: a ZeroMQ context to share, if one already exists.
        """
        RPCServer.__init__(self, namespace, interrupter)
        ZMQServerMixin.__init__(self, port, context)

class Interrupter(threading.Thread):
    """Interrupter runs in a background thread and creates KeyboardInterrupt
    events in the main thread when requested to do so."""
    def __init__(self):
        super().__init__(name='InterruptServer', daemon=True)
        self._armed = False
        self.start()

    @contextlib.contextmanager
    def armed(self):
        self._armed = True
        try:
            yield
        finally:
            self._armed = False

    def run(self):
        self.running = True
        while self.running:
            message = self._receive()
            logger.debug('Interrupt received: {}, armed={}', message, self._armed)
            if message == 'interrupt' and self._armed:
                os.kill(os.getpid(), signal.SIGINT)

    def _receive(self):
        raise NotImplementedError()

class ZMQInterrupter(Interrupter):
    def __init__(self, port, context=None):
        """InterruptServer subclass that uses ZeroMQ PUSH/PULL to communicate with clients.
        Parameters:
            port: a string ZeroMQ port identifier, like 'tcp://127.0.0.1:5555'.
            context: a ZeroMQ context to share, if one already exists.
        """
        self.context = context if context is not None else zmq.Context()
        self.socket = self.context.socket(zmq.PULL)
        self.socket.bind(port)
        super().__init__()

    def run(self):
        try:
            super().run()
        finally:
            self.socket.close()

    def _receive(self):
        return str(self.socket.recv(), encoding='ascii')

