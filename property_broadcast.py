import zmq
import threading
import collections
import traceback
import trie

class PropertyServer:
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
    def __init__(self, verbose=False):
        self.properties = {}
        self.verbose = verbose
        
    def add_property(self, property_name, value):
        """Add a named property and provide an initial value.
        Returns a callback to call when the property's value has changed."""
        self.properties[property_name] = value
        def change_callback(value):
            self._publish_update(property_name, value)
        return change_callback

    def update_property(self, property_name, value):
        """Inform the server that the property has a new value"""
        self._publish_update(property_name, value)

    def property_decorator(self, property_name):
        """Return a property decorator that will auto-update the named
        property when the setter is called. (See class documentation for
        example.)"""
        propertyserver = self
        class serverproperty(property):
            def __set__(self, obj, value):
                super().__set__(obj, value)
                propertyserver._publish_update(property_name, value)
        return serverproperty

    def _publish_update(self, property_name, value):
        """Send out an update to the clients"""
        self.properties[property_name] = value
        if self.verbose:
            print('updating property: {} to {}'.format(property_name, value))

class ZMQServer(PropertyServer):
    def __init__(self, port, context=None, verbose=False):
        """PropertyServer subclass that uses ZeroMQ PUB/SUB to send out updates.
        Arguments:
            port: a string ZeroMQ port identifier, like ''tcp://127.0.0.1:5555''.
            context: a ZeroMQ context to share, if one already exists.
        """
        super().__init__(verbose)
        self.context = context if context is not None else zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.bind(port)

    def _publish_update(self, property_name, value):
        super()._publish_update(property_name, value)
        # dump json first to catch "not serializable" errors before sending the first part of a two-part message
        json = zmq.utils.jsonapi.dumps(value)
        self.socket.send_string(property_name, flags=zmq.SNDMORE)
        self.socket.send(json)


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

    def subscribe_prefix(self, property_prefix, callback, valueonly=False):
        self.socket.setsockopt_string(zmq.SUBSCRIBE, property_prefix)
        super().subscribe_prefix(property_prefix, callback, valueonly)

    def _receive_update(self):
        property_name = self.socket.recv_string()
        assert(self.socket.getsockopt(zmq.RCVMORE))
        value = self.socket.recv_json()
        return property_name, value

        
if __name__ == '__main__':
    import sys
    mode = sys.argv[1]
    assert mode in ('client', 'server')
    if mode == 'client':
        zc = ZMQClient('tcp://127.0.0.1:6666')
        zc.subscribe('foo.bar', print)

    elif mode == 'server':
        zs = ZMQServer('tcp://127.0.0.1:6666')
        zs.add_property('foo.bar', 6)
        zs.update_property('foo.bar', 5)
    
    