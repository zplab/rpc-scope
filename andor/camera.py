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
    '''Note: rpc_acquisition.andor.andor.initialize(..) should be called before instantiating this class.'''
    def __init__(self):
        self._property_server = None
        # TODO: enumerate andor enum names and make name to enum id dict or python enum

    def get_exposure_time(self):
        return andor.GetFloat('ExposureTime')

    def set_exposure_time(self, exposure_time):
        andor.SetFloat('ExposureTime', exposure_time)

    def _attach_property_server(self, property_server):
        if self._property_server is not None:
            raise RuntimeError('Already attached to property_server.')
        self._property_server = property_server

    def _detach_property_server(self):
        if self._property_server is not None:
            pass

#   def _property_change_callback(feature, ):
