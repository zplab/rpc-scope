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

def server_main(rpc_port=None, property_port=None, verbose=False):
    if rpc_port is None:
        rpc_port = DEFAULT_RPC_PORT
    if property_port is None:
        property_port = DEFAULT_PROPERTY_PORT
        
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
    