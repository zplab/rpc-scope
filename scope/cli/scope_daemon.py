import argparse
import os.path
import sys


from . import base_daemon

from .. import scope_server
from ..config import scope_configuration
from ..util import logging
logger = logging.get_logger(__name__)

class ScopeServerRunner(base_daemon.Runner):
    def __init__(self, pidfile_path):
        super().__init__(name='Scope Server', pidfile_path=pidfile_path)

    def initialize_daemon(self):
        self.server = scope_server.ScopeServer(self.server_host)
        logger.info('Scope Server Ready (Listening on {})', self.server_host)

    def run_daemon(self):
        self.server.run()

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
    parser_start = subparsers.add_parser('start', help='start the microscope server, if not running')
    parser_start.add_argument('--public', action='store_true', help='Allow network connections to the server [default: allow only local connections]')
    parser_start.add_argument('--verbose', action='store_true', help='Log all RPC calls and property state changes.')
    parser_stop = subparsers.add_parser('stop', help='stop the microscope server, if running')
    parser_restart = subparsers.add_parser('restart', help='restart the microscope server, if not running')
    parser_restart.add_argument('--public', action='store_true', help='Allow network connections to the server [default: allow only local connections]')
    parser_restart.add_argument('--verbose', action='store_true', help='Log all RPC calls and property state changes.')
    args = parser.parse_args()

    try:
        runner, log_dir, config = make_runner()
        if args.command in ('stop', 'restart'):
            runner.terminate()
        if args.command in ('start', 'restart'):
            runner.server_host = config.Server.PUBLICHOST if args.public else config.Server.LOCALHOST
            runner.start(log_dir, args.verbose)
        if not args.command:
            print('No command specified!')
            parser.print_help()
    except Exception as e:
        if args.debug:
            traceback.print_exc(file=sys.stderr)
        else:
            sys.stderr.write(str(e)+'\n')
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv))
