# This code is licensed under the MIT License (see LICENSE file for details)

import collections
import threading
import traceback
import zmq
from . import trie

class PropertyClient(threading.Thread):
    """A client for receiving property updates in a background thread.

    The background thread is automatically started when this object is constructed.
    To stop the thread, set the 'running' attribute to False.
    """
    def __init__(self, daemon=True):
        # properties is a local copy of tracked properties, in case that's useful
        self.properties = {}
        # callbacks is a dict mapping property names to lists of callbacks
        self.callbacks = collections.defaultdict(set)
        # prefix_callbacks is a trie used to match property names to prefixes
        # which were registered for "wildcard" callbacks.
        self.prefix_callbacks = trie.trie()
        super().__init__(name='PropertyClient', daemon=daemon)
        self.start()

    def subscribe_from(self, other):
        """Copy subscriptions from other PropertyClient"""
        for property_name, callbacks in other.callbacks.items():
            for callback, valueonly in callbacks:
                self.subscribe(property_name, callback, valueonly)
        for property_prefix, callbacks in other.prefix_callbacks.items():
            for callback, valueonly in callbacks:
                self.subscribe_prefix(property_prefix, callback, valueonly)

    def run(self):
        """Thread target: do not call directly."""
        self.running = True
        while True:
            property_name, value = self._receive_update()
            if not self.running:
                break
            self.properties[property_name] = value
            for callbacks in [self.callbacks[property_name]] + list(self.prefix_callbacks.values(property_name)):
                for callback, valueonly in callbacks:
                    try:
                        if valueonly:
                            callback(value)
                        else:
                            callback(property_name, value)
                    except Exception as e:
                        print('Caught exception in PropertyClient callback:')
                        traceback.print_exception(type(e), e, e.__traceback__)

    def stop(self):
        self.running = False
        self.join()

    def subscribe(self, property_name, callback, valueonly=False):
        """Register a callback to be called any time the named property is updated.
        If valueonly is True, the callback will be called as: callback(new_value);
        if valueonly is False, it will be called as callback(property_name, new_value).

        Multiple callbacks can be registered for a single property_name.
        """
        self.callbacks[property_name].add((callback, valueonly))

    def unsubscribe(self, property_name, callback, valueonly=False):
        """Unregister an exactly matching, previously registered callback.  If
        the same callback function is registered multiple times with identical
        property_name and valueonly parameters, only one registration is removed."""
        if property_name is None:
            raise ValueError('property_name parameter must not be None.')
        try:
            callbacks = self.callbacks[property_name]
            callbacks.remove((callback, valueonly))
        except KeyError:
            raise KeyError('No matching subscription found for property name "{}".'.format(property_name)) from None
        if not callbacks:
            del self.callbacks[property_name]

    def subscribe_prefix(self, property_prefix, callback):
        """Register a callback to be called any time a named property which is
        prefixed by the property_prefix parameter is updated. The callback is
        called as callback(property_name, new_value).

        Example: if property_prefix is 'camera.', then the callback will be called
        when 'camera.foo' or 'camera.bar' or any such property name is updated.
        An empty prefix ('') will match everything.

        Multiple callbacks can be registered for a single property_prefix.
        """
        if property_prefix not in self.prefix_callbacks:
            self.prefix_callbacks[property_prefix] = set()
        self.prefix_callbacks[property_prefix].add((callback, False))

    def unsubscribe_prefix(self, property_prefix, callback):
        """Unregister an exactly matching, previously registered callback.  If
        the same callback function is registered multiple times with identical
        property_prefix parameters, only one registration is removed."""
        if property_prefix is None:
            raise ValueError('property_prefix parameter must not be None.')
        try:
            callbacks = self.prefix_callbacks[property_prefix]
            callbacks.remove((callback, False))
        except KeyError:
            raise KeyError('No matching subscription found for property name "{}".'.format(property_prefix))
        if not callbacks:
            del self.prefix_callbacks[property_prefix]

    def _receive_update(self):
        """Receive an update from the server"""
        raise NotImplementedError()

class ZMQClient(PropertyClient):
    def __init__(self, addr, context=None, daemon=True):
        """PropertyClient subclass that uses ZeroMQ PUB/SUB to receive out updates.
        Parameters:
            addr: a string ZeroMQ port identifier, like 'tcp://127.0.0.1:5555'.
            context: a ZeroMQ context to share, if one already exists.
            daemon: exit the client when the foreground thread exits.
        """
        self.context = context if context is not None else zmq.Context()
        self.addr = addr
        self.socket = None
        self.connected = threading.Event()
        super().__init__(daemon)

    def run(self):
        try:
            super().run()
        finally:
            self.socket.close()

    def reconnect(self):
        self.connected.clear()
        self.connected.wait()

    def _connect(self):
        if self.socket is not None:
            self.socket.close()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.RCVTIMEO = 0 # we use poll to determine whether there's data to receive, so we don't want to wait on recv
        self.socket.LINGER = 0
        self.socket.connect(self.addr)
        for property_name in list(self.callbacks) + list(self.prefix_callbacks):
            self.socket.setsockopt_string(zmq.SUBSCRIBE, property_name)
        self.connected.set()

    def subscribe(self, property_name, callback, valueonly=False):
        self.connected.wait()
        self.socket.setsockopt_string(zmq.SUBSCRIBE, property_name)
        super().subscribe(property_name, callback, valueonly)
    subscribe.__doc__ = PropertyClient.subscribe.__doc__

    def unsubscribe(self, property_name, callback, valueonly=False):
        super().unsubscribe(property_name, callback, valueonly)
        self.connected.wait()
        self.socket.setsockopt_string(zmq.UNSUBSCRIBE, property_name)
    unsubscribe.__doc__ = PropertyClient.unsubscribe.__doc__

    def subscribe_prefix(self, property_prefix, callback):
        self.connected.wait()
        self.socket.setsockopt_string(zmq.SUBSCRIBE, property_prefix)
        super().subscribe_prefix(property_prefix, callback)
    subscribe_prefix.__doc__ = PropertyClient.subscribe_prefix.__doc__

    def unsubscribe_prefix(self, property_prefix, callback):
        super().unsubscribe_prefix(property_prefix, callback)
        self.connected.wait()
        self.socket.setsockopt_string(zmq.UNSUBSCRIBE, property_prefix)
    unsubscribe_prefix.__doc__ = PropertyClient.unsubscribe_prefix.__doc__

    def _receive_update(self):
        while self.running:
            if not self.connected.is_set():
                self._connect()
            if self.socket.poll(500): # 500 ms wait before checking self.running again
                # poll returns true of socket has data to recv
                property_name = self.socket.recv_string()
                assert(self.socket.getsockopt(zmq.RCVMORE))
                value = self.socket.recv_json()
                return property_name, value

