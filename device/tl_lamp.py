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

from .util import property_device

class TL_Lamp(property_device.PropertyDevice):
    def __init__(self, iotool, property_server=None, property_prefix=''):
        super().__init__(property_server, property_prefix)
        self._iotool = iotool
        self.set_enabled(False)
        self.set_intensity(255)

    def set_enabled(self, enable):
        """Turn lamp on or off.
        """
        self._iotool.execute(*self._iotool.commands.transmitted_lamp(enable=enable))
        self._update_property('enabled', enable)


    def set_intensity(self, value):
        """Set intensity to any value in the range [0, 255] for min to max.
        """
        self._iotool.execute(*self._iotool.commands.transmitted_lamp(intensity=value))
        self._update_property('intensity', value)
