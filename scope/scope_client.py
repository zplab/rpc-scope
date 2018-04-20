# This code is licensed under the MIT License (see LICENSE file for details)

import zmq
import time
import collections
import numpy
import threading
import contextlib

from .simple_rpc import rpc_client, property_client
from .util import transfer_ism_buffer
from .util import state_stack
from .config import scope_configuration

def _make_in_state_func(obj):
    # have to do this in a separate function for each new obj, and not in a loop!
    # otherwise previous values of "obj" get overwritten
    def in_state(**state):
        """Context manager to set a number of device parameters at once using
        keyword arguments. The old values of those parameters will be restored
        upon exiting the with-block."""
        return state_stack.in_state(obj, **state)
    return in_state

def _replace_in_state(scope):
    for qualname in scope._functions_proxied:
        if qualname == 'in_state':
            obj = scope
        elif qualname.endswith('.in_state'):
            parents, name = qualname.rsplit('.', maxsplit=1)
            obj = eval(parents, scope.__dict__)
        else:
            continue
        obj.in_state = _make_in_state_func(obj)

def _make_rpc_client(host, rpc_port, context, allow_interrupt):
    rpc_addr = scope_configuration.make_tcp_host(host, rpc_port)
    client = rpc_client.ZMQClient(rpc_addr, timeout_sec=10, context=context)

    server_config = scope_configuration.ConfigDict(client('_get_configuration'))
    addresses = scope_configuration.get_addresses(host, server_config)
    if allow_interrupt:
        client.enable_interrupt(addresses['interrupt'])
    client.enable_heartbeat(addresses['heartbeat'], server_config.server.HEARTBEAT_INTERVAL_SEC*1.5)
    image_transfer_client = rpc_client.ZMQClient(addresses['image_transfer_rpc'],
        timeout_sec=5, context=context)
    is_local, get_data = transfer_ism_buffer.client_get_data_getter(image_transfer_client)

    # define additional client wrapper functions
    def get_many_data(data_list):
        return [get_data(name) for name in data_list]
    def get_stream_data(return_values):
        images_names, timestamps, attempted_frame_rate = return_values
        return get_many_data(images_names), timestamps, attempted_frame_rate
    def get_autofocus_data(return_values):
        best_z, positions_and_scores = return_values[:2]
        if len(return_values) == 3:
            image_names = return_values[2]
            return best_z, positions_and_scores, get_many_data(image_names)
        else:
            return best_z, positions_and_scores

    client_wrappers = {
        'camera.acquire_image': get_data,
        'camera.next_image': get_data,
        'camera.stream_acquire': get_stream_data,
        'camera.acquisition_sequencer.run': get_many_data,
        'camera.autofocus.autofocus': get_autofocus_data,
        'camera.autofocus.autofocus_continuous_move': get_autofocus_data
    }
    scope = client.proxy_namespace(client_wrappers)
    if hasattr(scope, 'camera'):
        # use a special RPC channel (the "image transfer" connection) devoted to just
        # getting image names and images from the server. This allows us to grab the
        # latest image from the camera, even when the main connection to the scope
        # is tied up with a blocking call (like autofocus).
        def latest_image():
            name, timestamp, frame_number = image_transfer_client('latest_image')
            return get_data(name), timestamp, frame_number
        latest_image.__doc__ = scope.camera.latest_image.__doc__
        scope.camera.latest_image = latest_image

        #monkeypatch in a image sequence acquisition context manager
        @contextlib.contextmanager
        def image_sequence_acquisition(frame_count=1, trigger_mode='Internal', **camera_params):
            """Context manager to begin and automatically end an image sequence acquisition."""
            scope.camera.start_image_sequence_acquisition(frame_count, trigger_mode, **camera_params)
            try:
                yield
            finally:
                scope.camera.end_image_sequence_acquisition()
        scope.camera.image_sequence_acquisition = image_sequence_acquisition
        if not is_local:
            scope.camera.set_network_compression = get_data.set_network_compression

    _replace_in_state(scope) # monkeypatch in in_state context managers
    scope._get_data = get_data
    scope._is_local = is_local
    scope._rpc_client = client
    scope.send_interrupt = client.send_interrupt
    scope._image_transfer_client = image_transfer_client
    scope.configuration = server_config
    scope.host = host
    scope._addresses = addresses
    def clone():
        """Create an identical client with distinct ZMQ sockets, so that it may be safely used
        from a separate thread."""
        return _make_rpc_client(host, rpc_port, context, allow_interrupt)
    scope._clone = clone
    scope._lock_attrs() # prevent unwary users from setting new attributes that won't get communicated to the server
    # now set a 60-second timeout to allow really long blocking operations (heartbeat client will address RPC server death in this interval)
    client.timeout_sec = 60
    return scope

def client_main(host='127.0.0.1', rpc_port=None, subscribe_all=False, allow_interrupt=True):
    """Connect to the microscope on the specified host.

    Parameters:
        host: IP or hostname to connect to
        rpc_port: if not None, override default port number
        subscribe_all: if True, the scope_properties object will subscribe to
            all property updates from the scope server, so that its internal
            'properties' dictionary will stay up-to-date.

    Returns: scope, scope_properties
    """
    context = zmq.Context()
    if rpc_port is None:
        rpc_port = scope_configuration.get_config().server.RPC_PORT
    scope = _make_rpc_client(host, rpc_port, context, allow_interrupt)
    scope_properties = property_client.ZMQClient(scope._addresses['property'], context)
    if subscribe_all:
        # have the property client subscribe to all properties. Even with a no-op callback,
        # this causes the client to keep its internal 'properties' dictionary up-to-date
        scope_properties.subscribe_prefix('', lambda x, y: None)
        scope.rebroadcast_properties()
    return scope, scope_properties

class LiveStreamer:
    class Timeout(RuntimeError):
        pass

    def __init__(self, scope, scope_properties, image_ready_callback=None):
        """Class to help manage retrieving images from a camera in live mode.

        Parameters:
          scope, scope_properties: microscope client object and property client
              as returned by client_main()
          image_ready_callback: function to call in a background thread when an
              image from the camera is ready. This function MAY NOT call any
              functions on the scope (e.g. retrieving an image) and MAY NOT call
              the get_image() function of this class. It should be used solely
              to signal the main thread to retrieve the image in some way.

        Useful properties:
          live: is the camera in live mode?
          bit_depth: is the camera in 12 vs. 16 bit mode?

        Simple usage example: the following will pull down ten frames from the
        live image stream; streamer.get_image() will block until an image is
        ready.

        scope, scope_properties = client_main()
        streamer = LiveStreamer(scope, scope_properties)
        images = []
        for i in range(10):
            image, timestamp, frame_number = streamer.get_image()
            images.append(image)
        """
        self.scope = scope
        self.image_ready_callback = image_ready_callback
        self.image_received = threading.Event()
        self.live = scope.camera.live_mode
        self.latest_intervals = collections.deque(maxlen=10)
        self.bit_depth = scope.camera.bit_depth
        self._last_time = time.time()
        self.properties = scope_properties
        self.properties.subscribe('scope.camera.live_mode', self._live_change, valueonly=True)
        self.properties.subscribe('scope.camera.frame_number', self._image_update, valueonly=True)
        self.properties.subscribe('scope.camera.bit_depth', self._depth_update, valueonly=True)

    def detach(self):
        self.image_ready_callback = None
        self.properties.unsubscribe('scope.camera.live_mode', self._live_change, valueonly=True)
        self.properties.unsubscribe('scope.camera.frame_number', self._image_update, valueonly=True)
        self.properties.unsubscribe('scope.camera.bit_depth', self._depth_update, valueonly=True)

    def get_image(self, timeout=None):
        """Return the latest image retrieved from the camera, along with a
        timestamp (in camera timestamp units; use camera.timestamp_hz to convert
        to seconds) and the frame sequence number. If no new image has arrived
        since the previous call to get_image(), the function blocks until a
        new image has arrived.

        If the timeout elapses before an image is ready, a Timeout is raised. If
        no timeout is specified, the wait may not ever return if there is no next
        image.

        To determine whether an image is ready, use image_ready()"""
        self.image_received.wait()
        # get image before re-enabling image-receiving because if this is over the network, it could take a while
        try:
            image, timestamp, frame_number = self.scope.camera.latest_image()
            t = time.time()
            self.latest_intervals.append(t - self._last_time)
            self._last_time = t
        finally:
            self.image_received.clear()
        return image, timestamp, frame_number

    def image_ready(self):
        """Return whether an image is ready to be retrieved. If False, a
        call to get_image() will block until an image is ready."""
        return self.image_received.is_set()

    def get_fps(self):
        """Return the recent FPS obtained from the live stream."""
        if not self.latest_intervals:
            return 0
        return 1/numpy.mean(self.latest_intervals)

    def _live_change(self, live):
        # called in property_client's thread: note we can't do RPC calls
        self.live = live
        self.latest_intervals.clear()
        self._last_time = time.time()

    def _image_update(self, frame_number):
        # called in property client's thread: note we can't do RPC calls...
        if frame_number == -1:
            return
        self.image_received.set()
        if self.image_ready_callback is not None:
            self.image_ready_callback()

    def _depth_update(self, depth):
        self.bit_depth = depth
