from rpc_acquisition import simple_rpc
from rpc_acquisition import property_broadcast
import serial
import zmq

from rpc_acquisition import dm6000b

DEFAULT_RPC_PORT = 'tcp://127.0.0.1:6000'
DEFAULT_PROPERTY_PORT = 'tcp://127.0.0.1:6001'


def server_main(rpc_port=None, property_port=None, verbose=False, context=None):
    if rpc_port is None:
        rpc_port = DEFAULT_RPC_PORT
    if property_port is None:
        property_port = DEFAULT_PROPERTY_PORT
    
    if context is None:
        context = zmq.Context()

    property_server = property_broadcast.ZMQServer(property_port, context=context, verbose=verbose)
    
    root = simple_rpc.Namespace()
    root.scope = dm6000b.Scope(property_server, verbose=verbose)
    
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
