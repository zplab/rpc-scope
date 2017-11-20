# This code is licensed under the MIT License (see LICENSE file for details)

import zmq
import threading
import queue

from zplib import datafile

from ..util import logging
logger = logging.get_logger(__name__)

class PropertyServer(threading.Thread):
    """Server for publishing changes to properties (i.e. (key, value) pairs) to
    other clients.

    There are three options for informing the server that a value has changed:
    (1) The add_property() method returns a callback that can be called with
        the new value.
    (2) The update_property() method can be called directly with the property
        name and new value.
    (3) The property_decorator() method can be used to generate a custom
        property decorator that auto-updates, e.g.:

        server = PropertyServer()

        class Foo:
            def __init__(self):
                self._x = 5

            @server.property_decorator('Foo.x')
            def x(self):
                return self._x

            @x.setter
            def x(self, value):
                self._x = value

    """
    def __init__(self):
        super().__init__(daemon=True)
        self.properties = {}
        self.task_queue = queue.Queue()
        self.running = True
        self.start()

    def run(self):
        while self.running:
            property_name, value = self.task_queue.get() # block until something's in the queue
            self._publish_update(property_name, value)

    def rebroadcast_properties(self):
        """Re-send an update about all known property values. Useful for
        clients that have just connected and want to learn about the current
        state."""
        for property_name, value in self.properties.items():
            self.task_queue.put((property_name, value))

    def add_property(self, property_name, value):
        """Add a named property and provide an initial value.
        Returns a callback to call when the property's value has changed."""
        self.properties[property_name] = value
        def change_callback(value):
            self.update_property(property_name, value)
        return change_callback

    def update_property(self, property_name, value):
        """Inform the server that the property has a new value"""
        self.properties[property_name] = value
        logger.debug('updating property: {} to {}', property_name, value)
        self.task_queue.put((property_name, value))

    def property_decorator(self, property_name):
        """Return a property decorator that will auto-update the named
        property when the setter is called. (See class documentation for
        example.)"""
        propertyserver = self
        class serverproperty(property):
            def __set__(self, obj, value):
                super().__set__(obj, value)
                propertyserver.update_property(property_name, value)
        return serverproperty

    def _publish_update(self, property_name, value):
        raise NotImplementedError()

class ZMQServer(PropertyServer):
    def __init__(self, port, context=None):
        """PropertyServer subclass that uses ZeroMQ PUB/SUB to send out updates.
        Parameters:
            port: a string ZeroMQ port identifier, like 'tcp://127.0.0.1:5555'.
            context: a ZeroMQ context to share, if one already exists.
        """
        self.context = context if context is not None else zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.bind(port)
        super().__init__()

    def run(self):
        try:
            super().run()
        finally:
            self.socket.close()

    def _publish_update(self, property_name, value):
        # dump json first to catch "not serializable" errors before sending the first part of a two-part message
        json = datafile.json_encode_compact_to_bytes(value)
        self.socket.send_string(property_name, flags=zmq.SNDMORE)
        self.socket.send(json)
