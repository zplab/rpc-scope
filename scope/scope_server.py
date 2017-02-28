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
import threading
import json
import pathlib

from .util import logging
from .util import base_daemon
from .config import scope_configuration

logger = logging.get_logger(__name__)

class ScopeServer(base_daemon.Runner):
    def __init__(self):
        self.base_dir = pathlib.Path(scope_configuration.CONFIG_DIR)
        self.log_dir = self.base_dir / 'scope_server_logs'
        self.arg_file = self.base_dir / 'server_options.json'
        super().__init__(name='Scope Server', pidfile_path=self.base_dir / 'scope_server.pid')

    def start(self):
        with self.arg_file.open('r') as f:
            args = json.load(f)
        self.config = scope_configuration.get_config()
        self.host = self.config.server.PUBLICHOST if args['public'] else self.config.server.LOCALHOST
        super().start(self.log_dir, args['verbose'])

    # function is to be run only when NOT running as a daemon
    def status(self):
        is_running = self.is_running()
        if not is_running:
            print('Microscope server is NOT running.')
        else:
            print('Microscope server is running (PID {}).'.format(self.get_pid()))
            client_tester = ScopeClientTester()
            connected = lambda: client_tester.connected # wait for connection to be established
            if _wait_for_it(connected, 'Establishing connection to scope server'):
                print('Microscope server is responding to new connections.')
            else:
                raise RuntimeError('Could not communicate with microscope server')

    def stop(self, force=False):
        self.assert_daemon()
        pid = self.get_pid()
        if force:
            self.kill() # send SIGKILL -- immeiate exit
        else:
            self.terminate() # send SIGTERM -- allow for cleanup
        exited = lambda: not base_daemon.is_valid_pid(pid) # wait for pid to become invalid (i.e. process no longer is running)
        if _wait_for_it(exited, 'Waiting for server to terminate'):
            print('Microscope server is stopped.')
        else:
            raise RuntimeError('Could not terminate microscope server')

    # overrides from base_daemon.Runner to implement server behavior
    def initialize_daemon(self):
        # do scope imports here so any at-import debug logging gets properly recorded
        from . import scope
        from .simple_rpc import rpc_server
        from .simple_rpc import property_server
        from .simple_rpc import heartbeat
        from .util import transfer_ism_buffer

        addresses = scope_configuration.get_addresses(self.host)
        self.context = zmq.Context()
        self.heartbeat_server = heartbeat.ZMQServer(addresses['heartbeat'],
            interval_sec=self.config.server.HEARTBEAT_INTERVAL_SEC, context=self.context)
        property_update_server = property_server.ZMQServer(addresses['property'], context=self.context)
        scope_controller = scope.Scope(property_update_server)
        scope_controller._sleep = time.sleep # way to provide a no-op RPC call for testing...

        image_transfer_namespace = Namespace()
        # add transfer_ism_buffer as hidden elements of the namespace, which RPC clients can use for seamless buffer sharing
        image_transfer_namespace._transfer_ism_buffer = transfer_ism_buffer
        if hasattr(scope_controller, 'camera'):
            image_transfer_namespace.latest_image=scope_controller.camera.latest_image
        image_transfer_server = rpc_server.BackgroundBaseZMQServer(image_transfer_namespace,
            addresses['image_transfer_rpc'], context=self.context)
        interrupter = rpc_server.ZMQInterrupter(addresses['interrupt'], context=self.context)
        self.scope_server = rpc_server.ZMQServer(scope_controller, interrupter,
            addresses['rpc'], context=self.context)
        logger.info('Scope Server Ready (Listening on {})', self.host)

    def run_daemon(self):
        try:
            self.scope_server.run()
        finally:
            self.context.term()


class ScopeClientTester(threading.Thread):
    def __init__(self):
        self.connected = False
        super().__init__(daemon=True)
        self.start()

    def run(self):
        from . import scope_client
        scope_client.client_main()
        self.connected = True

class Namespace:
    pass

def _wait_for_it(wait_condition, message, wait_time=15, output_interval=0.5, sleep_time=0.1):
    wait_iters = int(wait_time // sleep_time)
    output_iters = int(output_interval // sleep_time)
    condition_true = False
    print('(' + message + '.', end='', flush=True)
    for i in range(wait_iters):
        condition_true = wait_condition()
        if condition_true:
            break
        if i % output_iters == 0:
            print('.', end='', flush=True)
        time.sleep(sleep_time)
    print(')')
    return condition_true
