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

class ScopeClient:
    _HEARTBEAT_SEC = 3
    _scope = None # set to not none in instances when connected

    def __init__(self, host='127.0.0.1', allow_interrupt=True, auto_connect=True):
        self.host = host
        self._allow_interrupt = allow_interrupt

        context = zmq.Context()
        addresses = scope_configuration.get_addresses(host)
        interrupt_addr = addresses['interrupt'] if allow_interrupt else None
        kws = dict(heartbeat_sec=self._HEARTBEAT_SEC, timeout_sec=5, context=context)
        self._rpc_client = rpc_client.ZMQClient(addresses['rpc'], interrupt_addr, **kws)
        self._image_transfer_client = rpc_client.ZMQClient(addresses['image_transfer_rpc'], **kws)
        del kws['timeout_sec'] # no timeout for property_client since it's a receive channel
        self.properties = property_client.ZMQClient(addresses['property'], **kws)

        self._ping = self._rpc_client.proxy_function('_ping')
        self._sleep = self._rpc_client.proxy_function('_sleep')
        self.send_interrupt = self._rpc_client.send_interrupt
        self._connected = False
        if auto_connect:
            self._connect()

    def _can_connect(self):
        with self._rpc_client.timeout_sec(1):
            try:
                self._sleep(0) # TODO: change to _ping when all scope servers are updated
                return True
            except rpc_client.RPCError:
                return False

    def _connect(self):
        if not self._can_connect():
            raise RuntimeError(f'Cannot communicate with microscope server at {self.host}.')

        is_local, get_data = transfer_ism_buffer.client_get_data_getter(self._image_transfer_client)

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

        with self._rpc_client.timeout_sec(10):
            # the full API description can take a few secs to gether and pull over a slow network
            scope = self._rpc_client.proxy_namespace(client_wrappers)
        if hasattr(scope, 'camera'):
            # use a special RPC channel (the "image transfer" connection) devoted to just
            # getting image names and images from the server. This allows us to grab the
            # latest image from the camera, even when the main connection to the scope
            # is tied up with a blocking call (like autofocus).
            def latest_image():
                name, timestamp, frame_number = self._image_transfer_client('latest_image')
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
        scope._lock_attrs() # prevent unwary users from setting new attributes that won't get communicated to the server
        # now set a 60-second timeout to allow really long blocking operations
        self._rpc_client._timeout_ms = 60 * 1000

        self._get_data = get_data
        self._is_local = is_local
        self._functions_proxied = scope._functions_proxied
        for attr in dir(scope):
            if not attr.startswith('_'):
                setattr(self, attr, getattr(scope, attr))
        self._connected = True
        self._scope = scope

    def reconnect(self):
        self._rpc_client.reconnect()
        self._image_transfer_client.reconnect()
        self.properties.reconnect()

    def _clone(self, connect_timeout):
        """Create an identical client with distinct ZMQ sockets, so that it may be safely used
        from a separate thread."""
        is_connected = self._scope is not None
        return type(self)(self.host, self._allow_interrupt, auto_connect=is_connected)

    def __setattr__(self, name, value):
        if self._scope is not None:
            if hasattr(self, name):
                raise AttributeError(f'Attribute "{name}" cannot be modified.')
            else:
                raise AttributeError(f'Attribute "{name}" is not known, so its state cannot be communicated to the server.')
        else:
            super().__setattr__(name, value)


def _replace_in_state(scope):
    for qualname in scope._functions_proxied:
        if qualname == 'in_state':
            obj = scope
        elif qualname.endswith('.in_state'):
            parents, name = qualname.rsplit('.', maxsplit=1)
            obj = eval(parents, scope.__dict__)
        else:
            continue
        # deep magic to make state_stack.StateStackDevice.in_state act like a
        # bound method of obj, such that obj acts as the implicit "self" parameter:
        # https://docs.python.org/3/howto/descriptor.html#functions-and-methods
        obj.in_state = state_stack.StateStackDevice.in_state.__get__(obj)


class LiveStreamer:
    class Timeout(RuntimeError):
        pass

    def __init__(self, scope, image_ready_callback=None):
        """Class to help manage retrieving images from a camera in live mode.

        Parameters:
          scope: microscope client, instance of ScopeClient
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

        scope = ScopeClient()
        streamer = LiveStreamer(scope)
        images = []
        for i in range(10):
            image, timestamp, frame_number = streamer.get_image()
            images.append(image)
        """
        self.scope = scope
        self.image_ready_callback = image_ready_callback
        self.image_received = threading.Event()
        if hasattr(scope, 'camera'):
            self.live = scope.camera.live_mode
            self.bit_depth = scope.camera.bit_depth
        else:
            self.live = False
            self.bit_depth = '16 Bit'
        self.latest_intervals = collections.deque(maxlen=10)
        self._last_time = time.time()
        self.scope.properties.subscribe('scope.camera.live_mode', self._live_change, valueonly=True)
        self.scope.properties.subscribe('scope.camera.frame_number', self._image_update, valueonly=True)
        self.scope.properties.subscribe('scope.camera.bit_depth', self._depth_update, valueonly=True)

    def detach(self):
        self.image_ready_callback = None
        self.scope.properties.unsubscribe('scope.camera.live_mode', self._live_change, valueonly=True)
        self.scope.properties.unsubscribe('scope.camera.frame_number', self._image_update, valueonly=True)
        self.scope.properties.unsubscribe('scope.camera.bit_depth', self._depth_update, valueonly=True)

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
