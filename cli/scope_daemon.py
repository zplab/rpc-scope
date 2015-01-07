import argparse
import os
import os.path
import signal
import sys
import shutil

from daemon import daemon
from daemon import runner

from .. import scope_server
from ..config import scope_configuration
from ..util import logging
logger = logging.get_logger(__name__)

def terminate_handler(signal_number, stack_frame):
    """Signal handler for end-process signals."""
    logger.warn('Caught termination signal {}. Terminating.', signal_number)
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
        """Start the scope server daemon process."""
        if runner.is_pidfile_stale(self.pidfile):
            self.pidfile.break_lock()

        # better to try to lock the pidfile here to avoid any race conditions, but
        # managing the release through potentially-failing detach_process_context()
        # calls sounds... tricky. TODO: do it anyway?
        if self.pidfile.is_locked():
            raise RuntimeError('Scope server is already running')

        homedir = os.path.expanduser('~')
        daemon.prevent_core_dump()
        daemon.set_signal_handlers(SIGNAL_MAP)
        daemon.close_all_open_files(exclude={sys.stderr.fileno()})
        daemon.change_working_directory(homedir)
        #initialize logging
        logging.set_verbose(verbose)
        logging.attach_file_handlers(log_dir)
        logger.info('Starting Scope Server')

        # detach parent process. Note: ZMQ and camera don't work in child process
        # after a fork. ZMQ contexts don't work, and andor finalize functions hang.
        # Thus we need to init these things AFTER detaching the process via fork().
        # In order to helpfully print messages to stderr from the child process,
        # we use a custom detach_process_context that pipes stderr back to the
        # parent's stderr. (Otherwise the stderr would just spew all over the
        # terminal after the parent exits, which is ugly.)
        detach_process_context()
        try:
            self.pidfile.acquire()
            #initialize scope server
            server = scope_server.ScopeServer(server_host)

            logger.info('Scope Server Ready (Listening on {})', server_host)

            # detach stderr logger, and redirect python-generated output to /dev/null
            # (preventing anything that tries to print to / read from these streams from
            # throwing an error)
            logging.detach_console_handler()
            sys.stdin.close() # doing redirect_stream on sys.stdin somehow breaks subsequent logging. TODO: why?
            #daemon.redirect_stream(sys.stdin, None)
            daemon.redirect_stream(sys.stdout, None)
            # below closes pipe to parent that was redirected from old stderr by detach_process_context
            # which allows parent to exit...
            daemon.redirect_stream(sys.stderr, None)
        except:
            logger.error('Scope server could not initialize after becoming daemonic:', exc_info=True)
            self.pidfile.release()
            raise

        try:
            server.run()
        except Exception:
            logger.warn('Scope server terminating due to unhandled exception:', exc_info=True)
        finally:
            self.pidfile.release()


    def signal(self, sig):
        """Send a signal to the daemon process specified in the current PID file."""
        if not self.pidfile.is_locked():
            raise RuntimeError('Scope daemon is not running? (PID file "{}" not locked.)'.format(self.pidfile.path))

        if runner.is_pidfile_stale(self.pidfile):
            self.pidfile.break_lock()
        else:
            pid = self.pidfile.read_pid()
            os.kill(pid, sig)

    def stop(self):
        self.signal(signal.SIGTERM)


def detach_process_context():
    """Detach the process context from parent and session.

       Detach from the parent process and session group, allowing the
       parent to exit while this process continues running.

       This version, unlike that in daemon.py, pipes the stderr to the parent,
       which then sends that to its stderr.
       This way, the parent can report on child messages until the child
       decides to close sys.stderr.

       Reference: “Advanced Programming in the Unix Environment”,
       section 13.3, by W. Richard Stevens, published 1993 by Addison-Wesley."""

    r, w = os.pipe() # these are file descriptors, not file objects
    try: # fork 1
        pid = os.fork()
    except OSError as e:
        raise RuntimeError('First fork failed: [{}] {}'.format(e.errno, e.strerror))

    if pid:
        # parent
        os.close(w) # use os.close() to close a file descriptor
        r = os.fdopen(r) # turn r into a file object
        shutil.copyfileobj(r, sys.stderr, 1) # stream output of pipe to stderr
        os._exit(0)
    # child
    os.close(r) # don't need read end
    os.setsid()
    try: # fork 2
        pid = os.fork()
        if pid:
            # parent
            os._exit(0)
    except OSError as e:
        raise RuntimeError('Second fork failed: [{}] {}'.format(e.errno, e.strerror))

    # child
    os.dup2(w, sys.stderr.fileno()) # redirect stderr to pipe that goes to original parent
    os.close(w)

def main(argv):
    # scope_server [start --host --verbose | stop]
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
    try:
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
    except Exception as e:
        logger.warn('Error: {}', e)

if __name__ == '__main__':
    import sys
    main(sys.argv)
