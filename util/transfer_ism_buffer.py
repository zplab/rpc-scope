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
import zlib
import platform
import collections
import time

import ism_buffer

_ism_buffer_registry = collections.defaultdict(list)

def server_create_array(name, shape, dtype, order):
    """Create a numpy array view onto an ISM_Buffer shared memory region
    identified by the given name.

    The array retains a reference to the original ISM_Buffer object, so the
    shared memory region will be retained until the returned array is
    deallocated. If a separate process opens the named ISM_Buffer before the
    array goes away, then the ISM_Buffer will stay open (due to its own internal
    refcount).
    """
    array = ism_buffer.new(name, shape, dtype, order).asarray()
    return array

def server_register_array_for_transfer(name, array):
    """Register a named, ISM_Buffer-backed array with the server that is going
    to be transfered to another process. Once the other process obtains the
    ISM_Buffer, it must call the appropriate get_data() function (provided by
    client_get_data_getter()), which will ensure that the _release_array()
    function gets called."""
    _ism_buffer_registry[name].append(array)

def _release_array(name):
    """Remove the named, ISM_Buffer-backed array from the transfer registry,
    allowing it to be deallocated if nobody else on the server process is
    retaining any references. Return the named array."""
    return _ism_buffer_registry[name].pop()

def _server_release_array(name):
    """Remove the named, ISM_Buffer-backed array from the transfer registry,
    allowing it to be deallocated if nobody else on the server process is
    retaining any references. Does not return the named array, so this function
    is safe to call over RPC (which does not know how to send numpy arrays)."""
    _release_array(name)

def _server_pack_data(name, compressor='blosc', **compressor_args):
    """Pack the data in the named ISM_Buffer into bytes for transfer over
    the network (or other serialization).
    Valid compressor values are:
      - None: pack raw image bytes
      - 'blosc': use the fast, modern BLOSC compression library
      - 'zlib': use older, more widely supported zlib compression
    compressor_args are passed to zlib.compress() or blosc.compress() directly."""

    array = _release_array(name) # get the array and release it from the list of to-be-transfered arrays
    dtype_str = numpy.lib.format.dtype_to_descr(array.dtype)
    if array.flags.f_contiguous:
        order = 'F'
    elif array.flags.c_contiguous:
        order = 'C'
    else:
        array = numpy.asfortranarray(array)
        order = 'F'
    descr = json.dumps((dtype_str, array.shape, order)).encode('ascii')
    output = bytearray(struct.pack('<H', len(descr))) # put the len of the descr in a 2-byte uint16
    output += descr
    if compressor is None:
        output += memoryview(array.flatten(order=order))
    elif compressor == 'zlib':
        output += zlib.compress(array.flatten(order=order)), **compressor_args)
    elif compressor == 'blosc':
        import blosc
        # because blosc.compress can't handle a memoryview, we need to use blosc.compress_ptr
        output += blosc.compress_ptr(array.ctypes.data, array.size, typesize=array.dtype.itemsize, **compressor_args)
    else:
        raise RuntimeError('un-recognized compressor')
    return output

def _client_unpack_data(buf, compressor='blosc'):
    """Unpack (on the client side) data packed (on the server side) by _server_pack_data().
    The compressor name passed to _server_pack_data() must also be passed
    to this function."""
    # buf comes from a ZMQ zero-copy memoryview, which unfortunately currently
    # is stored as an un-sliceable 0-dim buffer. So we have to make a copy.
    # Also, blosc.decompress can't yet handle a memoryview object either, so
    # we'd need it as a bytes object at that point anyway.
    # TODO: try removing the bytes(buf) line in mid-2015 to see if they have accepted my patches to fix these issues.
    buf = bytes(buf)
    header_len = struct.unpack_from('<H', buf[:2])[0]
    dtype, shape, order = json.loads(bytes(buf[2:header_len+2]).decode('ascii'))
    array_buf = buf[header_len+2:]
    if compressor is None:
        data = array_buf
    elif compressor == 'zlib':
        data = zlib.decompress(array_buf)
    elif compressor == 'blosc':
        import blosc
        data = blosc.decompress(array_buf)
    return numpy.ndarray(shape, dtype=dtype, order=order, buffer=data)

def _server_get_node():
    return platform.node()

def client_get_data_getter(rpc_client, force_remote=False):
    """Return a callable, get_data(), which given an ISM_Buffer name, returns
    a numpy array containing the data from that buffer. If the server and client
    are on the same host (as determined by comparing platform.node() on both),
    then get_data() will give an array that is a view onto the ISM_Buffer. This
    is a fast, zero-copy operation. If the server and client are on different
    hosts, then the data will be packed and serialized over RPC. In this case,
    get_data() will have a method, 'set_network_compression()' to allow the
    amount of compression applied to the packed data to be tuned."""
    if force_remote:
        is_local = False
    else:
        is_local = rpc_client('_transfer_ism_buffer._server_get_node') == platform.node()

    if is_local: # on same machine -- use ISM buffer directly
        def get_data(name):
            array = ism_buffer.open(name).asarray()
            rpc_client('_transfer_ism_buffer._server_release_array', name)
            return array
    else: # pipe data over network
        class GetData:
            def __init__(self):
                self.compressor_args = {}
                try:
                    import blosc
                    self.compressor = 'blosc'
                    self.compressor_args['cname'] = 'lz4'
                except ImportError:
                    self.compressor = 'zlib'
                    self.compressor_args['level'] = 2

            def set_network_compression(self, compressor, **compressor_args):
                """Set the type of compression applied to images sent over the
                network.

                Valid compressor values are:
                  - None: pack raw image bytes
                  - 'blosc': use the fast, modern BLOSC compression library
                  - 'zlib': use older, more widely supported zlib compression
                compressor_args are passed to zlib.compress() or blosc.compress() directly."""
                self.compressor = compressor
                self.compressor_args = compressor_args

            def __call__(self, name):
                data = rpc_client('_transfer_ism_buffer._server_pack_data', name, self.compressor, **self.compressor_args)
                return _client_unpack_data(data, self.compressor)
        get_data = GetData()
    return is_local, get_data
