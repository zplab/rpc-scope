import runpy
import pathlib
import shutil

"""To use a non-default config file, before anything else, import this module
and set the CONFIG_FILE value to a filesystem path.
"""

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

class _Config:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            if not k.startswith('_'):
                setattr(self, k, v)

def _load_config(config_file):
    module_globals = runpy.run_path(config_file)
    return _Config(**module_globals)
