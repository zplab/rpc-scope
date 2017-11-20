# This code is licensed under the MIT License (see LICENSE file for details)

import logging
import gzip
import pathlib
import sys

def get_formatter():
    return logging.Formatter('>{asctime}\t{levelname}\t{name}\t{message}', datefmt='%Y-%m-%d %H:%M:%S', style='{')

def get_logger(name):
    """Get a logger for a specific purpose. Basic usage is to for each module that needs logging,
    call 'logger = logging.get_logger(__name__)' to set a module-level global logger."""
    return StyleAdapter(logging.getLogger(name))

# Workaround for the fact that by default logging messages must use old-style %-formatting.
# We define a special log message class and LoggerAdapter class to address this.
class FormattedLogMessage:
    def __init__(self, fmt, args):
        self.fmt = fmt
        self.args = args

    def __str__(self):
        return self.fmt.format(*self.args)

class StyleAdapter(logging.LoggerAdapter):
    def __init__(self, logger):
        self.logger = logger

    def log(self, level, msg, *args, **kwargs):
        if self.isEnabledFor(level):
            self.logger._log(level, FormattedLogMessage(msg, args), (), **kwargs)

    def addHandler(self, handler):
        self.logger.addHandler(handler)

    def log_exception(self, preamble):
        exc_info = sys.exc_info()
        self.warn('{} {}', preamble, exc_info[1]) # warn with the basic exception message
        self.debug('Detailed information', exc_info=exc_info) # log traceback at debug level

def gz_log_namer(name):
    return name + '.gz'

def gz_log_rotator(source_name, dest_name):
    source = pathlib.Path(source_name)
    if source.exists():
        with open(source_name, 'rb') as src, gzip.open(dest_name, 'wb') as dst:
            dst.writelines(src)
        source.unlink()

def delete_log_rotator(source_name, dest_name):
    source = pathlib.Path(source_name)
    if source.exists():
        source.unlink()
