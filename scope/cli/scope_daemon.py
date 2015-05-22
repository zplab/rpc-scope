import argparse
import os.path
import sys
import time
import threading
import json

from ..util import base_daemon
from .. import scope_server
from .. import scope_client
from ..config import scope_configuration
from ..util import json_encode
from ..util import logging
logger = logging.get_logger(__name__)

class ScopeServerRunner(base_daemon.Runner):
    def __init__(self, pidfile_path):
        super().__init__(name='Scope Server', pidfile_path=pidfile_path)

    # function is to be run only when not running as a daemon
    def status(self):
        is_running = self.is_running()
        if is_running:
            print('Microscope server is running (PID {}).'.format(self.get_pid()))
            client_tester = ScopeClientTester()
            print('(Establishing connection to scope server', end='', flush=True)
            for i in range(40):
                if client_tester.connected:
                    break
                else:
                    print('.', end='', flush=True)
                    time.sleep(0.5)
            print(')')
            if not client_tester.connected:
                raise RuntimeError('Could not communicate with microscope server')
            else:
                print('Microscope server is responding to new connections.')
        else:
            print('Microscope server is NOT running.')

    def stop(self, force=False):
        self.assert_daemon()
        pid = self.get_pid()
        if force:
            self.kill() # send SIGKILL -- immeiate exit
        else:
            self.terminate() # send SIGTERM -- allow for cleanup

        print('(Waiting for server to terminate', end='', flush=True)
        terminated = False
        for i in range(40):
            if base_daemon.is_valid_pid(pid):
                print('.', end='', flush=True)
                time.sleep(0.5)
            else:
                break
        print(')')
        if base_daemon.is_valid_pid(pid):
            raise RuntimeError('Could not terminate microscope server')
        else:
            print('Microscope server is stopped.')
    def initialize_daemon(self):
        self.server = scope_server.ScopeServer(self.server_host)
        logger.info('Scope Server Ready (Listening on {})', self.server_host)

    def run_daemon(self):
        self.server.run()

class ScopeClientTester(threading.Thread):
    def __init__(self):
        self.connected = False
        super().__init__(daemon=True)
        self.start()

    def run(self):
        scope_client.client_main()
        self.connected = True

def make_runner(base_dir='~'):
    base_dir = os.path.realpath(os.path.expanduser(base_dir))
    pidfile_path = os.path.join(base_dir, 'scope_server.pid')
    configfile_path = os.path.join(base_dir, 'scope_configuration.py')
    log_dir = os.path.join(base_dir, 'scope_logs')
    #initialize scope config
    scope_configuration.CONFIG_FILE = configfile_path
    # if it doesn't exist, make it so that it can be customized.
    scope_configuration.create_config_file_if_necessary()
    config = scope_configuration.get_config()
    runner = ScopeServerRunner(pidfile_path)
    return runner, log_dir, config

def main(argv):
    parser = argparse.ArgumentParser(description='microscope server control')
    parser.add_argument('--debug', action='store_true', help='show full stack traces on error')
    subparsers = parser.add_subparsers(help='sub-command help', dest='command')
    subparsers.required = True
    parser_start = subparsers.add_parser('start', help='start the microscope server, if not running')
    parser_start.add_argument('--public', action='store_true', help='Allow network connections to the server [default: allow only local connections]')
    parser_start.add_argument('--verbose', action='store_true', help='Log all RPC calls and property state changes.')
    parser_stop = subparsers.add_parser('stop', help='stop the microscope server, if running')
    parser_stop.add_argument('-f', '--force', action='store_true', help='forcibly kill the server process')
    parser_restart = subparsers.add_parser('restart', help='restart the microscope server, if running')
    parser_restart.add_argument('-f', '--force', action='store_true', help='forcibly kill the server process')
    parser_status = subparsers.add_parser('status', help='report whether the microscope server is running')
    args = parser.parse_args()

    try:
        runner, log_dir, config = make_runner()
        server_args = os.path.join(log_dir, 'server_options.json')
        if args.command == 'status':
            runner.status()
        if args.command in {'stop', 'restart'}:
            runner.stop(args.force)
        if args.command == 'restart':
            with open(server_args, 'r') as f:
                server_args = json.load(f)
            args.public = server_args['public']
            args.verbose = server_args['verbose']
        if args.command == 'start':
            with open(server_args, 'w') as f:
                json_encode.encode_legible_to_file(dict(public=args.public, verbose=args.verbose), f)
        if args.command in {'start', 'restart'}:
            runner.server_host = config.Server.PUBLICHOST if args.public else config.Server.LOCALHOST
            runner.start(log_dir, args.verbose)
    except Exception as e:
        if args.debug:
            traceback.print_exc(file=sys.stderr)
        else:
            sys.stderr.write(str(e)+'\n')
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv))
