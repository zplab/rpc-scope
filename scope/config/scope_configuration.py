# This code is licensed under the MIT License (see LICENSE file for details)

"""To use a non-default config file, before anything else, import this module
and set the CONFIG_FILE value to a filesystem path.
"""

import runpy
import pathlib
import shutil

from . import default_config

CONFIG_DIR = pathlib.Path('/usr/local/scope')
CONFIG_FILE = CONFIG_DIR / 'scope_configuration.py'

def make_tcp_host(host, port):
    return 'tcp://{}:{}'.format(host, port)

def get_addresses(host=None, config=None):
    if config is None:
        config = get_config()
    if host is None:
        host = config.server.LOCALHOST
    return dict(
        rpc=make_tcp_host(host, config.server.RPC_PORT),
        interrupt=make_tcp_host(host, config.server.RPC_INTERRUPT_PORT),
        property=make_tcp_host(host, config.server.PROPERTY_PORT),
        image_transfer_rpc=make_tcp_host(host, config.server.IMAGE_TRANSFER_RPC_PORT),
        heartbeat=make_tcp_host(host, config.server.HEARTBEAT_PORT)
     )

_CONFIG = None

def get_config():
    global _CONFIG
    if _CONFIG is None:
        if CONFIG_DIR.exists():
            if not CONFIG_FILE.exists():
                shutil.copyfile(default_config.__file__, str(CONFIG_FILE))
            _CONFIG = runpy.run_path(str(CONFIG_FILE))['scope_configuration']
        else: # no CONFIG_DIR
            _CONFIG = default_config.scope_configuration
     # return a new ConfigDict every time to prevent mutation of the global state
    return ConfigDict(_CONFIG)

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
        try:
            value = self[name]
        except:
            raise AttributeError(name)
        if isinstance(value, dict):
            value = ConfigDict(value)
        return value

    def __dir__(self):
        return super().__dir__() + list(self.keys())
