import json
import numpy
import gzip
import io
import ctypes
import platform
import collections

import ism_buffer

_ism_buffer_registry = collections.defaultdict(list)

def server_create_array(name, shape, dtype, order):
    array = ism_buffer.new(name, shape, dtype, order).asarray()
    return array

def server_register_array(name, array):
    _ism_buffer_registry[name].append(array)
    
def _server_release_array(name):
    _ism_buffer_registry[name].pop()

def _server_pack_ism_data(name, compresslevel=2, stolen_reference=True):
    buffer = ism_buffer.open(name, stolen_reference=stolen_reference)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=compresslevel) as f:
        f.write(buffer.descr) # json encoding of (dtype, shape, order)
        f.write(b'\0')
        f.write(ctypes.string_at(buffer.data, buffer.data._length_))
    return buf.getvalue()

def _client_unpack_ism_data(buf):
    data = gzip.decompress(buf)
    header_end = data.find(b'\0')
    dtype, shape, order = json.loads(data[:header_end].decode('ascii'))
    return numpy.ndarray(shape, dtype=dtype, order=order, buffer=data, offset=header_end+1)

def _server_get_node():
    return platform.get_node()

def client_get_data_getter(rpc_client):
    is_local = client('_ism_buffer_utils._server_get_node') == platform.get_node():
    if is_local: # on same machine -- use ISM buffer directly
        def get_data(name, release=True):
            array = ism_buffer.open(name).asarray()
            if release:
                rpc_client('_ism_buffer_utils._server_release_array', name)
            return array
    else: # pipe data over network
        def get_data(name, release=True):
            data = rpc_client('_ism_buffer_utils._server_pack_ism_data', name)
            if release:
                rpc_client('_ism_buffer_utils._server_release_array', name)
            return _client_unpack_ism_data(data)
    return is_local, get_data
    