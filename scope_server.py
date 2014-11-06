import zmq
from . import simple_rpc
from . import scope
from . import scope_configuration as config

def server_main(rpc_port=None, rpc_interrupt_port=None, property_port=None, verbose=False, context=None):
    if rpc_port is None:
        rpc_port = config.Server.RPC_PORT
    if rpc_interrupt_port is None:
        rpc_interrupt_port = config.Server.RPC_INTERRUPT_PORT
    if property_port is None:
        property_port = config.Server.PROPERTY_PORT

    if context is None:
        context = zmq.Context()

    property_server = simple_rpc.property_server.ZMQServer(property_port, context=context, verbose=verbose)

    scope_ = scope.Scope(property_server, verbose=verbose)

    interrupter = simple_rpc.rpc_server.ZMQInterrupter(rpc_interrupt_port, context=context)
    rpc_server = simple_rpc.rpc_server.ZMQServer(scope_, interrupter, rpc_port, context=context, verbose=verbose)

    try:
        rpc_server.run()
    except KeyboardInterrupt:
        print('\nExiting gracefully in response to ctrl-c ...')
    if hasattr(scope_, 'camera'):
        scope_.camera._andor_image_server.stop()

def rpc_client_main(rpc_port=None, rpc_interrupt_port=None, context=None):
    if rpc_port is None:
        rpc_port = config.Server.RPC_PORT
    if rpc_interrupt_port is None:
        rpc_interrupt_port = config.Server.RPC_INTERRUPT_PORT
        
    client = simple_rpc.rpc_client.ZMQClient(rpc_port, rpc_interrupt_port, context)
    scope = client.proxy_namespace()
    return client, scope

def property_client_main(property_port=None, context=None):
    if property_port is None:
        property_port = config.Server.PROPERTY_PORT
    client = simple_rpc.property_client.ZMQClient(property_port, context)
    return client
