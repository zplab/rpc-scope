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

_at_err_dict = {
    1: 'NOTINITIALISED',
    2: 'NOTIMPLEMENTED',
    3: 'READONLY',
    4: 'NOTREADABLE',
    5: 'NOTWRITABLE',
    6: 'OUTOFRANGE',
    7: 'INDEXNOTAVAILABLE',
    8: 'INDEXNOTIMPLEMENTED',
    9: 'EXCEEDEDMAXSTRINGLENGTH',
    10: 'CONNECTION',
    11: 'NODATA',
    12: 'INVALIDHANDLE',
    13: 'TIMEDOUT',
    14: 'BUFFERFULL',
    15: 'INVALIDSIZE',
    16: 'INVALIDALIGNMENT',
    17: 'COMM',
    18: 'STRINGNOTAVAILABLE',
    19: 'STRINGNOTIMPLEMENTED',
    20: 'NULL_FEATURE',
    21: 'NULL_HANDLE',
    22: 'NULL_IMPLEMENTED_VAR',
    23: 'NULL_READABLE_VAR',
    24: 'NULL_READONLY_VAR',
    25: 'NULL_WRITABLE_VAR',
    26: 'NULL_MINVALUE',
    27: 'NULL_MAXVALUE',
    28: 'NULL_VALUE',
    29: 'NULL_STRING',
    30: 'NULL_COUNT_VAR',
    31: 'NULL_ISAVAILABLE_VAR',
    32: 'NULL_MAXSTRINGLENGTH',
    33: 'NULL_EVCALLBACK',
    34: 'NULL_QUEUE_PTR',
    35: 'NULL_WAIT_PTR',
    36: 'NULL_PTRSIZE',
    37: 'NOMEMORY',
    38: 'DEVICEINUSE',
    100: 'HARDWARE_OVERFLOW',
    1002: 'AT_ERR_INVALIDOUTPUTPIXELENCODING',
    1003: 'AT_ERR_INVALIDINPUTPIXELENCODING',
    1004: 'AT_ERR_INVALIDMETADATAINFO'
}

class AndorError(RuntimeError):
    pass

def _at_errcheck(result, func, args):
    if result != 0:
        raise AndorError(_at_err_dict[result])
    return args

# NB: Callbacks should return AT_CALLBACK_SUCCESS, or, equivalently, 0
FeatureCallback = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_wchar_p, ctypes.c_void_p)

ANDOR_INFINITE = 0xFFFFFFFF
AT_FALSE = 0
AT_CALLBACK_SUCCESS = 0
