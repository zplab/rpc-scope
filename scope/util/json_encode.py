# The MIT License (MIT)
#
# Copyright (c) 2014-2015 WUSTL ZPLAB
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

class Encoder(json.JSONEncoder):
    """JSON encoder that is smart about converting iterators and numpy arrays to
    lists, and converting numpy scalars to python scalars.

    Caution: it is absurd to send large numpy arrays over the wire this way. Use
    the transfer_ism_buffer tools to send large data.
    """
    def default(self, o):
        try:
            return super().default(o)
        except TypeError as x:
            if isinstance(o, numpy.generic):
                item = o.item()
                if isinstance(item, numpy.generic):
                    raise x
                else:
                    return item
            try:
                return list(o)
            except:
                raise x


COMPACT_ENCODER = Encoder(separators=(',', ':'))
READABLE_ENCODER = Encoder(indent=4, sort_keys=True)

def encode_compact_to_bytes(data):
    return COMPACT_ENCODER.encode(data).encode('utf8')

def encode_legible_to_file(data, f):
    for chunk in READABLE_ENCODER.iterencode(data):
        f.write(chunk)
