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
# Authors: Erik Hvatum, Zach Pincus

import ctypes
from rpc_acquisition.andor import andor

class Camera:
    '''This class provides an abstraction of the raw Andor API ctypes shim found in
    rpc_acquisition.andor.andor.

    Note that rpc_acquisition.andor.andor.initialize(..) should be called once before
    instantiating this class.'''

    class _AT_Enum:
        def __init__(self, feature):
            self._feature = feature
            str_count = andor.GetEnumCount(self._feature)
            self._idxs_to_strs = [andor.GetEnumStringByIndex(feature, idx) for idx in range(str_count)]
            self._strs_to_idxs = {str_ : idx for idx, str_ in enumerate(self._idxs_to_strs)}

        def str_to_idx(self, str_):
            try:
                return self._strs_to_idxs[str_]
            except KeyError:
                raise ValueError('Value for {} must be one of {}.'.format(self._feature, self._idxs_to_strs))

        def idx_to_str(self, idx):
            return self._idxs_to_strs[idx]

    def __init__(self, property_server=None):
        self._property_server = None
        if property_server is not None:
            self._attach_property_server(property_server)
        # TODO: enumerate andor enum names and make name to enum id dict or python enum
        self._AuxiliaryOutSource = self._AT_Enum('AuxiliaryOutSource')

    def __del__(self):
        self._detach_property_server()

    def _attach_property_server(self, property_server):
        if self._property_server is not None:
            raise RuntimeError('Already attached to property_server.')
        self._property_server = property_server

    def _detach_property_server(self):
        if self._property_server is None:
            return

#   def _property_change_callback(feature, ):
#       pass

    def get_auxiliary_out_source(self):
        return self._AuxiliaryOutSource.idx_to_str(andor.GetEnumIndex('AuxiliaryOutSource'))

    def set_auxiliary_out_source(self, source):
        andor.SetEnumIndex('AuxiliaryOutSource', self._AuxiliaryOutSource.str_to_idx(source))

    def get_exposure_time(self):
        return andor.GetFloat('ExposureTime')

    def set_exposure_time(self, exposure_time):
        andor.SetFloat('ExposureTime', exposure_time)
