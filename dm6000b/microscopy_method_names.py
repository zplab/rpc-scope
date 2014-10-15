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
# Authors: Erik Hvatum

# Note that this list is backward as compared to the Leica documentation.  It's either reverse this
# list, or reverse every single method mask and method parameter list received from and sent to the
# DM6000B.  That being the case, it seems rather like Leica either confused bit and byte endianness,
# operating under the misapprehension that little-endian means the least significant BIT is first,
# or simply has this list reversed in their documentation, or is working around a bug in their own
# serial interface code.  Mucking up bit endianness in this manner is not as unlikely as it may seem
# given that serial (RS232) _is_ little-bit-endian and that the DM6000B communicates between its
# constituent components via serial.  This provides a number of opportunities for a trivial error to
# reverse masks, become set in stone, and thus require that all other parts of the system accomodate
# it.  Whatever the problem may be, reversing this list fixes it.
MICROSCOPY_METHOD_NAMES = [
    'method15',
    'method14',
    'BF/BF',
    'FLUO/DIC',
    'FLUO/PH',
    'FLUO',
    'IL POL',
    'IL DIC',
    'IL DF',
    'IL OBL',
    'IL BF',
    'TL POL',
    'TL DIC',
    'TL DF',
    'TL PH',
    'TL BF'
]

MICROSCOPY_METHOD_NAMES_TO_IDXS = {name : idx for idx, name in enumerate(MICROSCOPY_METHOD_NAMES)}
