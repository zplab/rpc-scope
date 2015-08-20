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

from .simple_rpc import rpc_server, property_server
from . import scope
from .util import transfer_ism_buffer
from .util import logging
from .config import scope_configuration

logger = logging.get_logger(__name__)

class Namespace:
    pass

class ScopeServer:
    def __init__(self, host):
        addresses = scope_configuration.get_addresses(host)
        self.context = zmq.Context()

        property_update_server = property_server.ZMQServer(addresses['property'], context=self.context)
        scope_controller = scope.Scope(property_update_server)
        async_namespace = Namespace()

        # add transfer_ism_buffer as hidden elements of the namespace, which RPC clients can use for seamless buffer sharing
        scope_controller._transfer_ism_buffer = transfer_ism_buffer
        async_namespace._transfer_ism_buffer = transfer_ism_buffer
        if hasattr(scope_controller, 'camera'):
            async_namespace.latest_image=scope_controller.camera.latest_image

        async_server = rpc_server.BackgroundBaseZMQServer(async_namespace,
            addresses['async_rpc'], context=self.context)
        interrupter = rpc_server.ZMQInterrupter(addresses['interrupt'], context=self.context)
        self.scope_server = rpc_server.ZMQServer(scope_controller, interrupter,
            addresses['rpc'], context=self.context)

    def run(self):
        try:
            self.scope_server.run()
        finally:
            self.context.term()

def simple_server_main(host, verbose=False):
    logging.set_verbose(verbose)
    server = ScopeServer(host)
    logger.info('Scope Server Ready (Listening on {})', host)
    try:
        server.run()
    except KeyboardInterrupt:
        return

if __name__ == '__main__':
    import argparse
    config = scope_configuration.get_config()
    parser = argparse.ArgumentParser(description="Run the microscope server")
    parser.add_argument("--public", action='store_true', help="Allow network connections to the server [default: allow only local connections]")
    parser.add_argument("--verbose", action='store_true', help="Print human-readable representations of all RPC calls and property state changes to stdout.")
    args = parser.parse_args()
    host = config.Server.PUBLICHOST if args.public else config.Server.LOCALHOST
    simple_server_main(host, verbose=args.verbose)
