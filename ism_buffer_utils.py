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
# Authors: Zach Pincus

import json
import numpy
import struct
import gzip
import io
import ctypes
import platform
import collections
import time

import ism_buffer

_ism_buffer_registry = collections.defaultdict(list)

def server_create_array(name, shape, dtype, order):
    array = ism_buffer.new(name, shape, dtype, order).asarray()
    return array

def server_register_array(name, array):
    _ism_buffer_registry[name].append(array)

def _release_array(name):
    return _ism_buffer_registry[name].pop()

def _server_release_array(name):
    """For calling over RPC: doesn't try to return the array"""
    _release_array(name)

def _server_pack_ism_data(name, compresslevel):
    ism_buf = ism_buffer.open(name)
    io_buf = io.BytesIO()
    if compresslevel is None:
        f = io_buf
    else:
        f = gzip.GzipFile(fileobj=io_buf, mode='wb', compresslevel=compresslevel)
    f.write(struct.pack('<H', len(ism_buf.descr)))
    f.write(ism_buf.descr) # json encoding of (dtype, shape, order)
    f.write(ctypes.string_at(ism_buf.data, size=len(ism_buf.data))) # ism_buf.data is uint8, so len == byte-size
    if compresslevel is not None:
        f.close()
    _release_array(name) # the array is now packed up so the server doesn't need to keep it anymore
    return io_buf.getvalue()

def _client_unpack_ism_data(buf):
    try:
        data = gzip.decompress(buf)
    except OSError:
        data = bytes(buf)
    header_len = struct.unpack('<H', data[:2])[0]
    dtype, shape, order = json.loads(data[2:header_len+2].decode('ascii'))
    return numpy.ndarray(shape, dtype=dtype, order=order, buffer=data, offset=header_len+2)

def _server_get_node():
    return platform.node()

def client_get_data_getter(rpc_client, force_remote=False):
    if force_remote:
        is_local = False
    else:
        is_local = rpc_client('_ism_buffer_utils._server_get_node') == platform.node()

    if is_local: # on same machine -- use ISM buffer directly
        def get_data(name):
            array = ism_buffer.open(name).asarray()
            rpc_client('_ism_buffer_utils._server_release_array', name)
            return array
    else: # pipe data over network
        class GetData:
            def __init__(self):
                # TODO: figure out a good way to auto-determine the compression level
                self.compresslevel = 2

            def set_network_compression(self, compresslevel=2):
                """Set the amount of compression applied to images streamed over the network:
                None = send raw bytes, or 0-9 indicates gzip compression level.
                None is best for a wired local connection; 2 is best for a wifi connection."""
                self.compresslevel = compresslevel

            def __call__(self, name):
                data = rpc_client('_ism_buffer_utils._server_pack_ism_data', name, self.compresslevel)
                return _client_unpack_ism_data(data)
        get_data = GetData()
    return is_local, get_data
