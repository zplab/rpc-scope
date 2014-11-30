# The MIT License (MIT)
#
# Copyright (c) 2014 WUSTL ZPLAB
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
import platform

from .simple_rpc import rpc_server, property_server
from .device import scope
from .device import scope_configuration as config
from .device.util import ism_buffer_utils

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
