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

from rpc_acquisition import message_device
from rpc_acquisition.dm6000b._shutters import _Shutters

class IL(message_device.LeicaAsyncDevice, _Shutters):
    '''IL represents an interface into elements of the scope primarily or exclusively
    used in Incident Light mode.  Like Stage and unlike ObjectiveTurret, the IL class
    does not represent a single function unit.'''
    def get_shutter(self):
        '''True: IL shutter open, False: IL shutter closed.  Note that setting this
        property is always a synchronous operation.'''
        return self._get_shutters()[1]

    def set_shutter(self, is_open):
        self._set_shutter(1, is_open)
