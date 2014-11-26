import functools

from . import simple_rpc
from . import scope_configuration as config
from . import ism_buffer_utils

def wrap_image_getter(namespace, func_name, get_data):
    function = getattr(namespace, func_name)
    @functools.wraps(function)
    def wrapped():
        return get_data(function())
    setattr(namespace, func_name, wrapped)

def wrap_images_getter(namespace, func_name, get_data):
    function = getattr(namespace, func_name)
    @functools.wraps(function)
    def wrapped():
        return [get_data(name) for name in function()]
        setattr(namespace, func_name, wrapped)

def rpc_client_main(rpc_port=None, rpc_interrupt_port=None, context=None):
    if rpc_port is None:
        rpc_port = config.Server.RPC_PORT
    if rpc_interrupt_port is None:
        rpc_interrupt_port = config.Server.RPC_INTERRUPT_PORT
        
    client = simple_rpc.rpc_client.ZMQClient(rpc_port, rpc_interrupt_port, context)
    scope = client.proxy_namespace()
    is_local, get_data = ism_buffer_utils.client_get_data_getter(client)
    scope._get_data = get_data
    scope._is_local = is_local
    if hasattr(scope, 'camera'):
        wrap_image_getter(scope.camera, 'acquire_image', get_data)
        wrap_image_getter(scope.camera, 'get_live_image', get_data)
        wrap_image_getter(scope.camera, 'get_next_image', get_data)
    if hasattr(scope, 'acquisition_sequencer'):
        wrap_images_getter(scope.acquisition_sequencer, 'run', get_data)
    return client, scope

def property_client_main(property_port=None, context=None):
    if property_port is None:
        property_port = config.Server.PROPERTY_PORT
    client = simple_rpc.property_client.ZMQClient(property_port, context)
    return client

class LiveStreamer:
    def __init__(self, scope, image_ready_callback):
        self.scope = scope
        self.image_ready_callback = image_ready_callback
        self.ready_to_receive = False
        self.image_received = False
        property_client.subscribe('scope.camera.live_mode', self._live_change, valueonly=True)
        property_client.subscribe('scope.camera.live_frame', self._live_update, valueonly=True)
    
    def get_image(self):
        assert self.image_received
        image = scope.camera.get_live_image()
        # get image before re-arming because if this is over the network, it could take a while
        self.ready_to_receive = True
        self.image_received = False
        return image, self.frame_no
        
    def _live_change(self, live):
        # called in property_client's thread: note we can't do RPC calls
        if live:
            self.ready_to_receive = True
            self.image_received = False
        else:
            self.ready_to_receive = False
            self.image_received = False
        
    def _live_update(self, frame_no):
        # called in property client's thread: note we can't do RPC calls
        if self.ready_to_receive:
            self.image_received = True
            self.ready_to_receive = False
            self.frame_no = frame_no
            self.image_ready_callback()
