import zmq
import platform

from .simple_rpc import rpc_server, property_server
from . import scope
from . import scope_configuration as config
from . import ism_buffer_utils

def server_main(rpc_port=None, rpc_interrupt_port=None, property_port=None, verbose=False, context=None):
    if rpc_port is None:
        rpc_port = config.Server.RPC_PORT
    if rpc_interrupt_port is None:
        rpc_interrupt_port = config.Server.RPC_INTERRUPT_PORT
    if property_port is None:
        property_port = config.Server.PROPERTY_PORT

    if context is None:
        context = zmq.Context()

    property_update_server = property_server.ZMQServer(property_port, context=context, verbose=verbose)

    scope_controller = scope.Scope(property_update_server, verbose=verbose)
    # add ism_buffer_utils as hidden elements of the namespace, which RPC clients can use for seamless buffer sharing
    scope_controller._ism_buffer_utils = ism_buffer_utils

    interrupter = rpc_server.ZMQInterrupter(rpc_interrupt_port, context=context, verbose=verbose)
    scope_server = rpc_server.ZMQServer(scope_controller, interrupter, rpc_port, context=context, verbose=verbose)

    print('******************\nScope Server Ready\n******************')
    try:
        scope_server.run()
    except KeyboardInterrupt:
        return

if __name__ == '__main__':
    server_main()
