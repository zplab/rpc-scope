# This code is licensed under the MIT License (see LICENSE file for details)

import logging
import logging.handlers
import pathlib
import sys

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

def log_exception(logger, preamble):
    exc_info = sys.exc_info()
    logger.warning('{} {}', preamble, exc_info[1]) # print out the basic exception message
    logger.debug('Detailed information', exc_info=exc_info) # log traceback at debug level

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
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / 'messages.log'
    debug_log_file = log_dir / 'debug.log'

    file_formatter = log_util.get_formatter()

    info_log_handler = logging.handlers.RotatingFileHandler(str(log_file),
        maxBytes=0, backupCount=8, delay=True) # keep 8 previous logs, but don't roll over automatically (maxBytes=0)
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
