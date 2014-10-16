from rpc_acquisition import message_device
from rpc_acquisition import message_manager
from rpc_acquisition import simple_rpc
from rpc_acquisition import property_broadcast
import serial
import zmq

from rpc_acquisition import dm6000b

SCOPE_PORT = '/dev/ttyScope'
SCOPE_BAUD = 115200
DEFAULT_RPC_PORT = 'tcp://127.0.0.1:6000'
DEFAULT_PROPERTY_PORT = 'tcp://127.0.0.1:6001'

class Scope(message_device.AsyncDeviceNamespace):
    def __init__(self, property_server, verbose=False):
        super().__init__()
        # need a timeout on the serial port so that the message manager thread can 
        # occasionally check it's 'running' attribute to decide if it needs to quit.
        self._scope_serial = serial.Serial(SCOPE_PORT, baudrate=SCOPE_BAUD, timeout=5)
        self._message_manager = message_manager.LeicaMessageManager(self._scope_serial, verbose=verbose)

        self.stage = dm6000b.Stage(self._message_manager)
        self.objective_turret = dm6000b.ObjectiveTurret(self._message_manager)

        # An object-oriented representation of the DM6000B and its sub-components
        # ("function units") where each sub-component is represented by a separate
        # object certainly involves more objects than cramming the entire
        # implementation into the main Scope object would.  However, the DM6000B
        # sub-components are truly discreet pieces of hardware and can be cleanly
        # represented as separate objects without any coupling, greatly clarifying
        # what would otherwise be an inscrutable hodgepodge.
        #
        # Nonetheless, users not familiar with every aspect of the DM6000B may
        # have trouble determining which sub-component is responsible for certain
        # things.  It is obvious enough that Scope.objective_turret must be used
        # to select a new objective, but less obvious that the lamp function unit
        # controls both the TL _and_ IL shutters, and less obvious still that the
        # stand function unit is responsible for microscopy mode (FLUO, BF, etc).
        # Therefore, to preserve implementation elegance and comprehensibility,
        # confusing function units are hidden and their properties are forwarded
        # from the Scope class.

        self._h_lamp = dm6000b.Lamp(self._message_manager)
        self.set_shutters_opened = self._h_lamp.set_shutters_opened
        self.set_tl_shutter_opened = self._h_lamp.set_tl_shutter_opened
        self.set_il_shutter_opened = self._h_lamp.set_il_shutter_opened
        self.get_shutters_opened = self._h_lamp.get_shutters_opened
        self.get_tl_shutter_opened = self._h_lamp.get_tl_shutter_opened
        self.get_il_shutter_opened = self._h_lamp.get_il_shutter_opened

        self._h_stand = dm6000b.Stand(self._message_manager)
        self.get_all_microscopy_methods = self._h_stand.get_all_microscopy_methods
        self.get_available_microscopy_methods = self._h_stand.get_available_microscopy_methods
        self.get_active_microscopy_method = self._h_stand.get_active_microscopy_method
        self.set_active_microscopy_method = self._h_stand.set_active_microscopy_method

def server_main(rpc_port=None, property_port=None, verbose=False, context=None):
    if rpc_port is None:
        rpc_port = DEFAULT_RPC_PORT
    if property_port is None:
        property_port = DEFAULT_PROPERTY_PORT
    
    if context is None:
        context = zmq.Context()

    property_server = property_broadcast.ZMQServer(property_port, context=context, verbose=verbose)
    
    root = simple_rpc.Namespace()
    root.scope = Scope(property_server, verbose=verbose)
    
    server = simple_rpc.ZMQServer(root, rpc_port, context=context, verbose=verbose)
    server.run()

def rpc_client_main(rpc_port=None):
    if rpc_port is None:
        rpc_port = DEFAULT_RPC_PORT
    client = simple_rpc.ZMQClient(rpc_port)
    root = client.proxy_namespace()
    return client, root

def property_client_main(property_port=None):
    if property_port is None:
        property_port = DEFAULT_PROPERTY_PORT
    client = property_broadcast.ZMQClient(property_port)
    return client
