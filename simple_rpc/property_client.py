# The MIT License (MIT)
#
# Copyright (c) 2014 WUSTL ZPLAB
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
# Authors: Zach Pincus, Erik Hvatum <ice.rikh@gmail.com>

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
        self.callbacks = collections.defaultdict(list)
        # prefix_callbacks is a trie used to match property names to prefixes
        # which were registered for "wildcard" callbacks.
        self.prefix_callbacks = trie.trie()
        super().__init__(name='PropertyClient', daemon=daemon)
        self.start()

    def run(self):
        """Thread target: do not call directly."""
        self.running = True
        while self.running:
            property_name, value = self._receive_update()
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

    def subscribe(self, property_name, callback, valueonly=False):
        """Register a callback to be called any time the named property is updated.
        If valueonly is True, the callback will be called as: callback(new_value);
        if valueonly is False, it will be called as callback(property_name, new_value).

        Multiple callbacks can be registered for a single property_name.
        """
        self.callbacks[property_name].append((callback, valueonly))

    def unsubscribe(self, property_name, callback, valueonly=False):
        """Unregister an exactly matching, previously registered callback.  If
        the same callback function is registered multiple times with identical
        property_name and valueonly parameters, only one registration is removed."""
        if property_name is None:
            raise ValueError('property_name parameter must not be None.')
        try:
            cbs = self.callbacks[property_name]
        except KeyError:
            raise KeyError('No subscription found for property name "{}".'.format(property_name))
        try:
            cb_idx = cbs.index((callback, valueonly))
        except ValueError:
            raise KeyError('At least one subscription was found for property name "{}", but none '.format(property_name) + \
                           'have the specified callback and valueonly parameters.')
        del cbs[cb_idx]
        if not cbs:
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
            self.prefix_callbacks[property_prefix] = []
        self.prefix_callbacks[property_prefix].append((callback, False))

    def unsubscribe_prefix(self, property_prefix, callback):
        """Unregister an exactly matching, previously registered callback.  If
        the same callback function is registered multiple times with identical
        property_prefix parameters, only one registration is removed."""
        if property_prefix is None:
            raise ValueError('property_prefix parameter must not be None.')
        try:
            cbs = self.prefix_callbacks[property_prefix]
        except KeyError:
            raise KeyError('No subscription found for property prefix "{}".'.format(property_prefix))
        try:
            cb_idx = cbs.index((callback, False))
        except ValueError:
            raise KeyError('At least one subscription was found for property prefix "{}", but none '.format(property_prefix) + \
                           'has the specified callback.')
        del cbs[cb_idx]
        if not cbs:
            del self.prefix_callbacks[property_prefix]

    def _receive_update(self):
        """Receive an update from the server"""
        raise NotImplementedError()

class ZMQClient(PropertyClient):
    def __init__(self, port, context=None, daemon=True):
        """PropertyClient subclass that uses ZeroMQ PUB/SUB to receive out updates.
        Arguments:
            port: a string ZeroMQ port identifier, like ''tcp://127.0.0.1:5555''.
            context: a ZeroMQ context to share, if one already exists.
            daemon: exit the client when the foreground thread exits.
        """
        self.context = context if context is not None else zmq.Context()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.connect(port)
        super().__init__(daemon)

    def subscribe(self, property_name, callback, valueonly=False):
        self.socket.setsockopt_string(zmq.SUBSCRIBE, property_name)
        super().subscribe(property_name, callback, valueonly)
    subscribe.__doc__ = PropertyClient.subscribe.__doc__

    def unsubscribe(self, property_name, callback, valueonly=True):
        super().unsubscribe(property_name, callback, valueonly)
        self.socket.setsockopt_string(zmq.UNSUBSCRIBE, property_name)
    unsubscribe.__doc__ = PropertyClient.unsubscribe.__doc__

    def subscribe_prefix(self, property_prefix, callback):
        self.socket.setsockopt_string(zmq.SUBSCRIBE, property_prefix)
        super().subscribe_prefix(property_prefix, callback)
    subscribe_prefix.__doc__ = PropertyClient.subscribe_prefix.__doc__

    def unsubscribe_prefix(self, property_prefix, callback):
        super().unsubscribe_prefix(property_prefix, callback)
        self.socket.setsockopt_string(zmq.UNSUBSCRIBE, property_prefix)
    unsubscribe_prefix.__doc__ = PropertyClient.unsubscribe_prefix.__doc__

    def _receive_update(self):
        property_name = self.socket.recv_string()
        assert(self.socket.getsockopt(zmq.RCVMORE))
        value = self.socket.recv_json()
        return property_name, value
