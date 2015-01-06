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

SIGNAL_MAP = {getattr(signal, sig): handler for sig, handler in
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

        logger.info('Starting Scope Server')
        homedir = os.path.expanduser('~')
        stderr_fd = sys.stderr.fileno()

        daemon.prevent_core_dump()
        daemon.set_signal_handlers(SIGNAL_MAP)
        daemon.close_all_open_files(exclude={stderr_fd})

        #initialize logging
        logging.set_verbose(verbose)
        logging.attach_file_handlers(log_dir)

        # detach parent process. Note: ZMQ and camera don't work right unless 
        # initialized in child process AFTER this detaching. Odd.
        # TODO: figure out a fix.
        daemon.detach_process_context()

        #initialize scope server
        server = scope_server.ScopeServer(server_host)


        # chroot to home dir
        try:
            daemon.change_root_directory(homedir)
        except daemon.DaemonOSEnvironmentError:
            logger.warn('Could not chroot to {}', homedir)


        logger.info('Scope Server Ready (Listening on {})', server_host)

        # detach stderr logger, close stderr, and redirect python-generated output to /dev/null
        logging.detach_console_handler()
        daemon.close_file_descriptor_if_open(stderr_fd)
        daemon.redirect_stream(sys.stdin, None)
        daemon.redirect_stream(sys.stdout, None)
        daemon.redirect_stream(sys.stderr, None)

        with self.pidfile:
            try:
                server.run()
            except Exception:
                logger.warn('Scope server terminating due to unhandled execption:', exc_info=True)


    def stop(self):
        """Exit the daemon process specified in the current PID file.
            """
        if not self.pidfile.is_locked():
            raise RuntimeError("PID file {} not locked".format(self.pidfile.path))

        if runner.is_pidfile_stale(self.pidfile):
            self.pidfile.break_lock()
        else:
            pid = self.pidfile.read_pid()
            os.kill(pid, signal.SIGTERM)


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
    args = parser.parse_args()

    runner = Runner(pidfile_path)

    if args.command == 'start':
        #initialize scope config
        scope_configuration.CONFIG_FILE = config_file
        # if it doesn't exist, make it so that it can be customized.
        scope_configuration.create_config_file_if_necessary()
        config = scope_configuration.get_config()
        server_host = config.Server.PUBLICHOST if args.public else config.Server.LOCALHOST

        runner.start(server_host, log_dir, args.verbose)

    elif args.command == 'stop':
        runner.stop()

if __name__ == '__main__':
    import sys
    main(sys.argv)
