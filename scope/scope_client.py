# This code is licensed under the MIT License (see LICENSE file for details)

import zmq
import time
import collections
import numpy
import threading
import contextlib

from .simple_rpc import rpc_client, property_client
from .util import transfer_ism_buffer
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
        if auto_connect:
            self._connect()

    def _can_connect(self):
        with self._rpc_client.timeout_sec(1):
            try:
                self._sleep(0) # TODO: change to _ping when all scope servers are updated
                return True
            except rpc_client.RPCError:
                return False

    def _is_connected(self):
        return self._scope is not None

    def _connect(self):
        if not self._can_connect():
            raise RuntimeError(f'Cannot communicate with microscope server at {self.host}.')
        with self._rpc_client.timeout_sec(10):
            # the full API description can take a few secs to gether and pull over a slow network
            scope = self._rpc_client.proxy_namespace()
        # now set a 60-second default timeout to allow long blocking rpc calls
        self._rpc_client._timeout_sec = 60

        is_local, get_data = transfer_ism_buffer.client_get_data_getter(self._image_transfer_client)

        if hasattr(scope, 'camera'):
            _patch_camera(scope.camera, get_data, self._image_transfer_client)
            if not is_local:
                scope.camera.set_network_compression = get_data.set_network_compression
            if hasattr(scope.camera, 'autofocus'):
                # set a 45-minute timeout to allow for FFT calculation if necessary
                scope.camera.autofocus.ensure_fft_ready._timeout_sec = 45*60
                # autofocus might be a bit slow too
                scope.camera.autofocus.autofocus._timeout_sec = 2*60
                scope.camera.autofocus.autofocus_continuous_move._timeout_sec = 2*60

        if hasattr(scope, 'stage'):
            # stage init can take more than our usual 60-second timeout
            scope.stage.reinit._timeout_sec = 2*60
            scope.stage.reinit_x._timeout_sec = 2*60
            scope.stage.reinit_y._timeout_sec = 2*60
            scope.stage.reinit_z._timeout_sec = 2*60

        _patch_in_state_context_managers(scope)
        scope._lock_attrs() # prevent unwary users from setting new attributes that won't get communicated to the server
        self._get_data = get_data
        self._is_local = is_local
        self._functions_proxied = scope._functions_proxied
        self._scope = scope

    def reconnect(self):
        self._rpc_client.reconnect()
        self._image_transfer_client.reconnect()
        self.properties.reconnect()

    def _clone(self):
        """Create an identical client with distinct ZMQ sockets, so that it may be safely used
        from a separate thread."""
        return type(self)(self.host, self._allow_interrupt, auto_connect=self._is_connected())

    def __setattr__(self, name, value):
        if self._scope is not None:
            if hasattr(self._scope, name):
                setattr(self._scope, name, value)
            elif not hasattr(self, name):
                raise AttributeError(f"Attribute '{name}' is not known, so its state cannot be communicated to the server.")
            else:
                raise AttributeError(f"Attribute '{name}' cannot be modified")
        else:
            super().__setattr__(name, value)

    def __getattr__(self, name):
        if self._scope is not None and hasattr(self._scope, name):
            return getattr(self._scope, name)
        raise AttributeError(f"'ScopeClient' object has no attribute '{name}'")

    def __dir__(self):
        listing = super().__dir__()
        if self._scope is not None:
            scope_list = set(dir(self._scope))
            scope_list.update(listing)
            listing = sorted(scope_list)
        return listing


def _patch_camera(camera, get_data, image_transfer_client):
    # ensure that the camera uses the proper data-transfer channels, and
    # monkeypatch the sequence acquisition context manager

    # define image transfer wrapper functions
    def get_many_data(image_names):
        return [get_data(name) for name in image_names]
    def get_data_and_metadata(return_values):
        image_name, timestamp, frame_number = return_values
        return get_data(image_name), timestamp, frame_number
    def get_stream_data(return_values):
        images_names, timestamps, attempted_frame_rate = return_values
        return get_many_data(images_names), timestamps, attempted_frame_rate
    def get_autofocus_data(return_values):
        best_z, positions_and_scores, image_names = return_values
        return best_z, positions_and_scores, get_many_data(image_names)

    camera.acquire_image._output_handler = get_data
    camera.next_image._output_handler = get_data
    camera.next_image_and_metadata._output_handler = get_data_and_metadata
    camera.stream_acquire._output_handler = get_stream_data
    if hasattr(camera, 'acquisition_sequencer'):
        camera.acquisition_sequencer.run._output_handler = get_many_data
    if hasattr(camera, 'autofocus'):
        camera.autofocus.autofocus._output_handler = get_autofocus_data
        camera.autofocus.autofocus_continuous_move._output_handler = get_autofocus_data

    # use a special RPC channel (the "image transfer" connection) devoted to just
    # getting image names and images from the server. This allows us to grab the
    # latest image from the camera, even when the main connection to the scope
    # is tied up with a blocking call (like autofocus).
    def latest_image():
        name, timestamp, frame_number = image_transfer_client('latest_image')
        return get_data(name), timestamp, frame_number
    latest_image.__doc__ = camera.latest_image.__doc__
    camera.latest_image = latest_image

    # monkeypatch image sequence acquisition context manager to work on client side
    @contextlib.contextmanager
    def image_sequence_acquisition(frame_count=1, trigger_mode='Internal', **camera_params):
        """Context manager to begin and automatically end an image sequence acquisition."""
        camera.start_image_sequence_acquisition(frame_count, trigger_mode, **camera_params)
        try:
            yield
        finally:
            camera.end_image_sequence_acquisition()
    camera.image_sequence_acquisition = image_sequence_acquisition

def _patch_in_state_context_managers(scope):
    # monkeypatch in_state context managers to work on client side
    for qualname in scope._functions_proxied:
        if qualname == 'in_state':
            obj = scope
        elif qualname.endswith('.in_state'):
            parents, name = qualname.rsplit('.', maxsplit=1)
            obj = eval(parents, scope.__dict__)
        else:
            continue
        _generate_in_state(obj)

def _generate_in_state(obj):
    # must do below in separate function for each obj so that the closure
    # works right (standard python bugaboo with generating closures in loops...)
    @contextlib.contextmanager
    def in_state(**state):
        """Context manager to set a number of device parameters at once using
        keyword arguments. The old values of those parameters will be restored
        upon exiting the with-block."""
        obj.push_state(**state)
        try:
            yield
        finally:
            obj.pop_state()
    obj.in_state = in_state


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
