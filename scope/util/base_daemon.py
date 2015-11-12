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

import os
import os.path
import signal
import errno
import sys
import shutil

from daemon import daemon
from daemon import runner
from lockfile import pidlockfile

from . import logging
logger = logging.get_logger(__name__)

def sigterm_handler(signal_number, stack_frame):
    """Signal handler for end-process signals."""
    logger.warn('Caught termination signal {}. Terminating.', signal_number)
    raise SystemExit('Terminating on signal {}'.format(signal_number))

DEFAULT_SIGNAL_MAP = {
    'SIGTSTP': signal.SIG_IGN,
    'SIGTTIN': signal.SIG_IGN,
    'SIGTTOU': signal.SIG_IGN,
    'SIGTERM': sigterm_handler
}

class Runner:
    def __init__(self, name, pidfile_path):
        self.name = name
        self.pidfile = pidlockfile.PIDLockFile(os.path.realpath(str(pidfile_path)), timeout=10)

    def initialize_daemon(self):
        pass

    def run_daemon(self):
        raise NotImplementedError()

    def start(self, log_dir, verbose, **signal_map):
        """Start the daemon process."""
        if runner.is_pidfile_stale(self.pidfile):
            self.pidfile.break_lock()

        # Is it better to try to lock the pidfile here to avoid any race conditions?
        # Managing the release through potentially-failing detach_process_context()
        # calls sounds... tricky.
        if self.pidfile.is_locked():
            raise RuntimeError('{} is already running'.format(self.name))

        homedir = os.path.expanduser('~')
        log_dir = os.path.realpath(log_dir)
        daemon.prevent_core_dump()
        for sig, handler in DEFAULT_SIGNAL_MAP.items():
            if sig not in signal_map:
                signal_map[sig] = handler
        daemon.set_signal_handlers({getattr(signal, sig):handler for sig, handler in signal_map.items()})
        daemon.close_all_open_files(exclude={sys.stdin.fileno(), sys.stdout.fileno(), sys.stderr.fileno()})
        daemon.change_working_directory(homedir)
        #initialize logging
        logging.set_verbose(verbose)
        logging.attach_file_handlers(log_dir)
        logger.info('Starting {}', self.name)

        # detach parent process. Note: ZMQ and camera don't work in child process
        # after a fork. ZMQ contexts don't work, and andor finalize functions hang.
        # Thus we need to init these things AFTER detaching the process via fork().
        # In order to helpfully print messages to stderr from the child process,
        # we use a custom detach_process_context that pipes stderr back to the
        # parent's stderr. (Otherwise the stderr would just spew all over the
        # terminal after the parent exits, which is ugly.)
        detach_process_context()
        with self.pidfile:
            try:
                #initialize scope server
                logger.debug('Initializing {}', self.name)
                self.initialize_daemon()
                # detach stderr logger, and redirect python-generated output to /dev/null
                # (preventing anything that tries to print to / read from these streams from
                # throwing an error)
                logging.detach_console_handler()
                daemon.redirect_stream(sys.stdin, None)
                daemon.redirect_stream(sys.stdout, None)
                # below also closes pipe to parent that was redirected from old stderr by
                # detach_process_contex, which allows parent to exit...
                daemon.redirect_stream(sys.stderr, None)
            except:
                logger.error('{} could not initialize after becoming daemonic:', self.name, exc_info=True)
                raise

            try:
                logger.debug('Running {}', self.name)
                self.run_daemon()
            except Exception:
                logger.error('{} terminating due to unhandled exception:', self.name, exc_info=True)

    def is_running(self):
        return self.pidfile.is_locked()

    def assert_daemon(self):
        if not self.is_running():
            raise RuntimeError('{} is not running (cannot find PID file "{}").'.format(self.name, self.pidfile.path))

    def get_pid(self):
        return self.pidfile.read_pid()

    def signal(self, sig):
        """Send a signal to the daemon process specified in the current PID file."""
        self.assert_daemon()

        if runner.is_pidfile_stale(self.pidfile):
            self.pidfile.break_lock()
        else:
            os.kill(self.get_pid(), sig)

    def terminate(self):
        """Send SIGTERM to the daemon: a handle-able request to cease."""
        self.signal(signal.SIGTERM)

    def kill(self):
        """Send SIGKILL to the daemon: a non-handle-able forcible exit."""
        self.signal(signal.SIGKILL)

def is_valid_pid(pid):
    try:
        os.kill(pid, signal.SIG_DFL)
        return True
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            # The specified PID does not exist
            return False

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

