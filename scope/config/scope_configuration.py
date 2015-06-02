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
# Author: Zach Pincus

"""To use a non-default config file, before anything else, import this module
and set the CONFIG_FILE value to a filesystem path.
"""

import runpy
import pathlib
import shutil

def _make_tcp_host(host, port):
    return 'tcp://{}:{}'.format(host, port)

def rpc_addr(host=None):
    config = get_config()
    if host is None:
        host = config.Server.LOCALHOST
    return _make_tcp_host(host, config.Server.RPC_PORT)

def interrupt_addr(host=None):
    config = get_config()
    if host is None:
        host = config.Server.LOCALHOST
    return _make_tcp_host(host, config.Server.RPC_INTERRUPT_PORT)

def property_addr(config, host=None):
    config = get_config()
    if host is None:
        host = config.Server.LOCALHOST
    return _make_tcp_host(host, config.Server.PROPERTY_PORT)

CONFIG_FILE = None
_CONFIG = None

def get_config():
    global _CONFIG
    if _CONFIG is None:
        if CONFIG_FILE is None:
            config_file = str(_get_default_config_path())
        else:
            config_file = CONFIG_FILE
        _CONFIG = _load_config(config_file)
    return _CONFIG

def create_config_file_if_necessary():
    if CONFIG_FILE is not None:
        config_file = pathlib.Path(CONFIG_FILE)
        if not config_file.exists():
            shutil.copyfile(str(_get_default_config_path()), str(config_file))

def _get_default_config_path():
    return pathlib.Path(__file__).parent / 'default_config.py'

class ConfigDict(dict):
    """dict subclass that supports attribute-style value access, as well
    as lookups into arbitrarily-nested dictionaries via dotted-namespace-style
    value access. Note that the nested dictionaries need not be ConfigDicts
    themselves.

    Example:
        b = {'bb': 6}
        c = {'cc': {'ccc': 7}}
        d = ConfigDict(a=5, b=b, c=c)
        d.a # 5
        d.b.bb # 6
        d.c.cc.ccc # 7
    """
    def __getattr__(self, name):
        value = self[name]
        if isinstance(value, dict):
            value = ConfigDict(value)
        return value

    def __dir__(self):
        return super().__dir__() + list(self.keys())

def _load_config(config_file):
    module_globals = runpy.run_path(config_file)
    return ConfigDict(module_globals)
