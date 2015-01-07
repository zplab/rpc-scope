# The MIT License (MIT)
#
# Copyright (c) 2014 WUSTL ZPLAB
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
import gzip

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

def get_logger(name):
    """Get a logger for a specific purpose. Basic usage is to for each module that needs logging,
    call 'logger = logging.get_logger(__name__)' to set a module-level global logger."""
    return _StyleAdapter(logging.getLogger(name))

def attach_file_handlers(log_dir):
    """Add logfile writers that will dump logs to the provided directory. One weekly rotating log will
    contain log messages at info or above, and one ephemeral log that is cleared every 30 minutes
    will contain debug-level messages."""
    log_dir = pathlib.Path(log_dir)
    if not log_dir.exists():
        log_dir.mkdir(parents=True)

    file_formatter = formatter = logging.Formatter('>{asctime}\t{levelname}\t{name}\t{message}', datefmt='%Y-%m-%d %H:%M:%S', style='{')

    # TODO: make a custom rotating handler that works like the timed handler, but just appends .1, .2, .3 etc.
    info_log_handler = logging.handlers.TimedRotatingFileHandler(str(log_dir / 'messages.log'),
        when='D', interval=7, backupCount=8) # roll over weekly
    info_log_handler.namer = _gz_log_namer
    info_log_handler.rotator = _gz_log_rotator
    info_log_handler.doRollover() # roll the log each time logging is started... sadly deletes old logs from same day. See TODO above
    info_log_handler.setLevel(logging.INFO)
    info_log_handler.setFormatter(file_formatter)
    logging.root.addHandler(info_log_handler)


    if logging.root.getEffectiveLevel() == logging.DEBUG:
        debug_log_handler = logging.handlers.TimedRotatingFileHandler(str(debug_log),
            when='M', interval=30, backupCount=1, delay=True) # roll over every half hour; don't create unless asked-for
        #debug_log_handler.rotator = _delete_log_rotator # required if backupCount=0, otherwise it never deletes the old log files
        debug_log_handler.doRollover() # roll over each time logging is started
        debug_log_handler.setLevel(logging.DEBUG)
        debug_log_handler.setFormatter(file_formatter)
        logging.root.addHandler(debug_log_handler)


# Workaround for the fact that by default logging messages must use old-style %-formatting.
# We define a special log message class and LoggerAdapter class to address this.
class _FormattedLogMessage:
    def __init__(self, fmt, args):
        self.fmt = fmt
        self.args = args

    def __str__(self):
        return self.fmt.format(*self.args)

class _StyleAdapter(logging.LoggerAdapter):
    def __init__(self, logger):
        self.logger = logger

    def log(self, level, msg, *args, **kwargs):
        if self.isEnabledFor(level):
            self.logger._log(level, _FormattedLogMessage(msg, args), (), **kwargs)

def _gz_log_namer(name):
    return name + '.gz'

def _gz_log_rotator(source_name, dest_name):
    source = pathlib.Path(source_name)
    if source.exists():
        with open(source_name, 'rb') as src, gzip.open(dest_name, 'wb') as dst:
            dst.writelines(src)
        source.unlink()

def _delete_log_rotator(source_name, dest_name):
    source = pathlib.Path(source_name)
    if source.exists():
        source.unlink()
