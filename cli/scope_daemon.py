import argparse
import os.path
import signal
import sys

from daemon import daemon
from daemon import runner

from .. import scope_server
from ..config import scope_configuration
from ..util import logging
logger = logging.get_logger(__name__)

def terminate_handler(signal_number, stack_frame):
    """ Signal handler for end-process signals."""
    logger.debug('Caught termination signal {}. Terminating.', signal_number)
    raise SystemExit('Terminating on signal {}'.format(signal_number))

SIGNAL_MAP = {sig: handler for sig, handler in
    {'SIGTSTP': signal.SIG_IGN,
     'SIGTTIN': signal.SIG_IGN,
     'SIGTTOU': signal.SIG_IGN,
     'SIGTERM': terminate_handler}.items()
    if hasattr(signal, sig)
}

class Runner:
    def __init__(self, pidfile_path):
        self.pidfile = runner.make_pidlockfile(pidfile_path, acquire_timeout=10)

    def start(self, server_host, log_dir, verbose):
        """Start the scope server daemon process"""
        if runner.is_pidfile_stale(self.pidfile):
            self.pidfile.break_lock()

        homedir = os.path.expanduser('~')
        stderr_fd = sys.stderr.fileno()

        daemon.prevent_core_dump()
        daemon.change_working_directory(homedir)
        daemon.set_signal_handlers(SIGNAL_MAP)
        daemon.close_all_open_files(exclude={stderr_fd})

        #initialize logging
        logging.set_verbose(verbose)
        logging.attach_file_handlers(log_dir)

        #initialize scope server
        server = scope_server.ScopeServer(server_host)

        #detach stderr logger, close stderr, and redirect python-generated output to /dev/null
        logging.detach_console_handler()
        daemon.close_file_descriptor_if_open(stderr_fd)
        daemon.redirect_stream(sys.stdin, None)
        daemon.redirect_stream(sys.stdout, None)
        daemon.redirect_stream(sys.stderr, None)

        # detach from controlling terminal and chroot to home dir
        daemon.detach_process_context()
        daemon.change_root_directory(homedir)

        with self.pidfile:
            try:
                logger.info('Starting microscope server.')
                server.run()
            except Exception:
                logger.warn('Scope server terminating due to unhandled execption:', exc_info=True)


    def _terminate_daemon_process(self):
        """Terminate the daemon process specified in the current PID file.
            """

    def stop(self):
        """Exit the daemon process specified in the current PID file.
            """
        if not self.pidfile.is_locked():
            raise RuntimeError("PID file {} not locked".format{self.pidfile.path})

        if runner.is_pidfile_stale(self.pidfile):
            self.pidfile.break_lock()
        else:
            pid = self.pidfile.read_pid()
            os.kill(pid, signal.SIGTERM)

    def restart(self):
        """ Stop, then start.
            """
        self.stop()
        self.start()


def main(argv):
    # scope_server [start --host --verbose | stop | restart]
    pidfile_path = os.path.expanduser('~/scope_server.pid')
    config_file = os.path.expanduser('~/scope_configuration.py')
    log_dir = os.path.expanduser('~/scope_logs')

    parser = argparse.ArgumentParser(description="microscope server control")
    subparsers = parser.add_subparsers(help='sub-command help', dest='command')
    parser_start = subparsers.add_parser('start', help='start the microscope server, if not running')
    parser_start.add_argument("--public", action='store_true', help="Allow network connections to the server [default: allow only local connections]")
    parser_start.add_argument("--verbose", action='store_true', help="Print human-readable representations of all RPC calls and property state changes to stdout.")
    parser_stop = subparsers.add_parser('stop', help='stop the microscope server, if running')
    parser_restart = subparsers.add_parser('restart', help='restart the microscope server, if running')
    args = parser.parse_args()

    runner = Runner(pidfile_path)

    if args.command == 'start':
        #initialize scope config
        scope_configuration.CONFIG_FILE = config_file
        # if it doesn't exist, make it so that it can be customized.
        scope_configuration.create_config_file_if_necessary()
        config = scope_configuration.get_config()
        server_host = config.Server.PUBLICHOST if args.public else config.Server.LOCALHOST

        runner.start(server_host, log_dir, config_file, args.verbose)

    elif args.command == 'stop':
        runner.stop()

    elif args.command == 'restart':
        runner.restart()

