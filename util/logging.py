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
# Authors: Zach Pincus <zpincus@wustl.edu>

import logging
import logging.handlers
import pathlib

from . import log_util

def set_verbose(verbose=True):
    if verbose:
        logging.root.setLevel(logging.DEBUG)
    else:
        logging.root.setLevel(logging.INFO)

console_handler = logging.StreamHandler() # no formatter: just prints bare messages to stderr

def attach_console_handler():
    logging.root.addHandler(console_handler)

def detach_console_handler():
    logging.root.removeHandler(console_handler)

# default logging initialization
attach_console_handler()
set_verbose(False)

get_logger = log_util.get_logger

def attach_file_handlers(log_dir):
    """Add logfile writers that will dump logs to the provided directory. One weekly rotating log will
    contain log messages at info or above, and one ephemeral log that is cleared every 30 minutes
    will contain debug-level messages.

    Debug log is only created if the the CURRENT logging level is DEBUG, so make sure to set the
    desired level before attaching handlers.
    """
    log_dir = pathlib.Path(log_dir)
    if not log_dir.exists():
        log_dir.mkdir(parents=True)

    log_file = log_dir / 'messages.log'
    debug_log_file = log_dir / 'debug.log'

    file_formatter = log_util.get_formatter()

    info_log_handler = logging.handlers.RotatingFileHandler(str(log_file),
        maxBytes=0, backupCount=8) # keep 8 previous logs, but don't roll over automatically (maxBytes=0)
    info_log_handler.doRollover() # roll the log each time logging is started...
    info_log_handler.setLevel(logging.INFO)
    info_log_handler.setFormatter(file_formatter)
    logging.root.addHandler(info_log_handler)

    if debug_log_file.exists():
        # nuke debug log -- either we're going to make a new one soon, or the old one is stale anyway
        debug_log_file.unlink()
    if logging.root.getEffectiveLevel() == logging.DEBUG:
        debug_log_handler = logging.handlers.RotatingFileHandler(str(debug_log_file),
            maxBytes=1024*1024*10, backupCount=0, delay=True) # keep only latest 10 MB of debug log; don't create unless asked-for
        debug_log_handler.setLevel(logging.DEBUG)
        debug_log_handler.setFormatter(file_formatter)
        logging.root.addHandler(debug_log_handler)
