# This code is licensed under the MIT License (see LICENSE file for details)

import json
import numpy
import struct
import zlib
import platform
import collections
import threading

import ism_buffer

_ism_buffer_registry = collections.defaultdict(list)
_registry_lock = threading.Lock()

def create_array(name, shape, dtype, order):
    """Create a numpy array view onto an ISM_Buffer shared memory region
    identified by the given name.

    The array retains a reference to the original ISM_Buffer object, so the
    shared memory region will be retained until the returned array is
    deallocated. If a separate process opens the named ISM_Buffer before the
    array goes away, then the ISM_Buffer will stay open (due to its own internal
    refcount).
    """
    return ism_buffer.new(name, shape, dtype, order).asarray()

def register_array_for_transfer(name, array):
    """Register a named, ISM_Buffer-backed array with the server that is going
    to be transfered to another process. Once the other process obtains the
    ISM_Buffer, it must call the appropriate get_data() function (provided by
    client_get_data_getter()), which will ensure that the _release_array()
    function gets called."""
    # A single image can get queued for transfer several times (i.e. if several
    # clients all want to grab the same live image). Appending it to a list
    # makes sure we can track the count of outgoing requests, so we don't free
    # things too soon.
    # Note that this function may be called simultaneously by two threads
    # via camera.latest_image running on the main thread and the image transfer
    # thread; or this function and _release_array might get called simultaneously.
    # Thus we protect mutating access to the registry.
    with _registry_lock:
        # the below is sufficiently atomic that simultaneous calls to this function
        # won't cause a problem (the default will only get created once),
        # but we don't want to be appending to an array that's simultaneously
        # getting deleted by _release_array.
        _ism_buffer_registry[name].append(array)

def release_array(name):
    """Remove the named, ISM_Buffer-backed array from the transfer registry,
    allowing it to be deallocated if nobody else on the server process is
    retaining any references. Return the named array."""
    arrays = _ism_buffer_registry[name]
    array = arrays.pop()
    with _registry_lock:
        # don't want another thread to register the same name after we here
        # decide that arrays is empty, but before we delete it, so synchronize
        # this section only.
        if not arrays:
            del _ism_buffer_registry[name]
    return array

def borrow_array(name):
    """Return the named array, while still keeping a reference in the registry
    for future transfer to a client."""
    return _ism_buffer_registry[name][-1]

def _server_release_array(name):
    """Remove the named, ISM_Buffer-backed array from the transfer registry,
    allowing it to be deallocated if nobody else on the server process is
    retaining any references. Does not return the named array, so this function
    is safe to call over RPC (which does not know how to send numpy arrays)."""
    release_array(name)

def _server_pack_data(name, compressor='blosc', downsample=None, **compressor_args):
    """Pack the data in the named ISM_Buffer into bytes for transfer over
    the network (or other serialization).
    Downsample parameter: int / None. If not None, only return every nth pixel.
    Valid compressor values are:
      - None: pack raw image bytes
      - 'blosc': use the fast, modern BLOSC compression library
      - 'zlib': use older, more widely supported zlib compression
    compressor_args are passed to zlib.compress() or blosc.compress() directly."""

    array = release_array(name) # get the array and release it from the list of to-be-transfered arrays
    if downsample:
        array = array[::downsample, ::downsample]
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
        has_level_arg = 'level' in compressor_args
        if len(compressor_args) - has_level_arg > 0:
            raise RuntimeError('"level" is the only valid valid zlib compression option.')
        zlib_compressor_args = [compressor_args['level']] if has_level_arg else []
        output += zlib.compress(array.flatten(order=order), *zlib_compressor_args)
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
    header_len = struct.unpack_from('<H', buf[:2])[0]
    dtype, shape, order = json.loads(bytes(buf[2:header_len+2]).decode('ascii'))
    array_buf = buf[header_len+2:]
    # NB: If this function exits with an exception involving zero-length slices, please upgrade your pyzmq
    # installation (the issue is known to be fixed pyzmq 14.6.0, and at the time this comment was written,
    # "pip-3.4 install pyzmq" grabbed 14.7.0).
    if compressor is None:
        data = array_buf
    elif compressor == 'zlib':
        data = zlib.decompress(array_buf)
    elif compressor == 'blosc':
        import blosc
        try:
            # This works as of June 2 (pyblosc git repo commit ID 487fe5531abc38faebd47b92a34991a1489a7ac3)
            data = blosc.decompress(array_buf)
        except TypeError:
            # However, as of Aug 11 2015, the version of pyblosc installed by pip-3.4 does not yet include
            # the fix, so most lab machines will fall through to the following legacy method, which copies
            # to a temporary intermediate buffer
            data = blosc.decompress(bytes(array_buf))
    array = numpy.ndarray(shape, dtype=dtype, order=order, buffer=data)
    array.flags.writeable = True
    return array

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
                self.downsample = None
                self.compressor_args = {}
                try:
                    import blosc
                    self.compressor = 'blosc'
                    self.compressor_args['cname'] = 'lz4'
                except ImportError:
                    self.compressor = 'zlib'
                    self.compressor_args['level'] = 2

            def set_network_compression(self, compressor, downsample=None, **compressor_args):
                """Set the type of compression applied to images sent over the
                network.

                Parameters:
                    compressor: what compression method to use. Valid choices:
                      - None: pack raw image bytes
                      - 'blosc': use the fast, modern BLOSC compression library
                      - 'zlib': use older, more widely supported zlib compression
                    downsample: int / None. If not None, return every nth pixel.
                    compressor_args: passed to zlib.compress() or blosc.compress() directly."""
                self.compressor = compressor
                self.compressor_args = compressor_args
                self.downsample = downsample

            def __call__(self, name):
                data = rpc_client('_transfer_ism_buffer._server_pack_data', name, self.compressor, self.downsample, **self.compressor_args)
                return _client_unpack_data(data, self.compressor)
        get_data = GetData()
    return is_local, get_data
