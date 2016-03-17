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
import time
import collections
import numpy
import threading

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

def _replace_in_state(client, scope):
    for qualname, doc, argspec in client('__DESCRIBE__'):
        if qualname == 'in_state':
            obj = scope
        elif qualname.endswith('.in_state'):
            parents, name = qualname.rsplit('.', maxsplit=1)
            obj = eval(parents, scope.__dict__)
        else:
            continue

        obj.in_state = _make_in_state_func(obj)

def _make_rpc_client(rpc_addr, interrupt_addr, image_transfer_addr, context=None):
    client = rpc_client.ZMQClient(rpc_addr, interrupt_addr, context)
    image_transfer_client = rpc_client.BaseZMQClient(image_transfer_addr, context)
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
    def get_config(config_dict):
        return scope_configuration.ConfigDict(config_dict)

    client_wrappers = {
        'get_configuration': get_config,
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
            return get_data(image_transfer_client('latest_image'))
        latest_image.__doc__ = scope.camera.latest_image.__doc__
        scope.camera.latest_image = latest_image

    _replace_in_state(client, scope)
    scope._get_data = get_data
    scope._is_local = is_local
    if not is_local:
        scope.camera.set_network_compression = get_data.set_network_compression
    scope._rpc_client = client
    scope._image_transfer_client = image_transfer_client
    scope._lock_attrs() # prevent unwary users from setting new attributes that won't get communicated to the server
    return scope

def client_main(host='127.0.0.1', context=None, subscribe_all=False):
    if context is None:
        context = zmq.Context()
    addresses = scope_configuration.get_addresses(host)
    scope = _make_rpc_client(addresses['rpc'], addresses['interrupt'], addresses['image_transfer_rpc'], context)
    scope_properties = property_client.ZMQClient(addresses['property'], context)
    if subscribe_all:
        # have the property client subscribe to all properties. Even with a no-op callback,
        # this causes the client to keep its internal 'properties' dictionary up-to-date
        scope_properties.subscribe_prefix('', lambda x, y: None)
        scope.rebroadcast_properties()
    return scope, scope_properties

class LiveStreamer:
    def __init__(self, scope, scope_properties, image_ready_callback=None):
        self.scope = scope
        self.image_ready_callback = image_ready_callback
        self.image_received = threading.Event()
        self.live = scope.camera.live_mode
        self.latest_intervals = collections.deque(maxlen=10)
        self.bit_depth = scope.camera.bit_depth
        self._last_time = time.time()
        scope_properties.subscribe('scope.camera.live_mode', self._live_change, valueonly=True)
        scope_properties.subscribe('scope.camera.frame_number', self._image_update, valueonly=True)
        scope_properties.subscribe('scope.camera.bit_depth', self._depth_update, valueonly=True)

    def get_image(self):
        self.image_received.wait()
        # get image before re-enabling image-receiving because if this is over the network, it could take a while
        try:
            image = self.scope.camera.latest_image()
            t = time.time()
            self.latest_intervals.append(t - self._last_time)
            self._last_time = t
            # stash our latest frame number, as self.frame_number could change if further updates occur
            # after we clear the image_received Event...
            frame_number = self.frame_number
        finally:
            self.image_received.clear()
        return image, frame_number

    def get_fps(self):
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
        # Note: if we've already received an image, but nobody on the main thread
        # has called get_image() to retrieve it, then just ignore subsequent
        # updates.
        if frame_number is -1:
            return
        self.frame_number = frame_number
        if not self.image_received.is_set():
            self.image_received.set()
            if self.image_ready_callback is not None:
                self.image_ready_callback()

    def _depth_update(self, depth):
        self.bit_depth = depth