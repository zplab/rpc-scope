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

from ..util import property_device

class TL_Lamp_Base(property_device.PropertyDevice):
    def __init__(self, iotool, property_server=None, property_prefix=''):
        super().__init__(property_server, property_prefix)
        self._iotool = iotool
        self.set_enabled(False)

    def set_enabled(self, enabled):
        """Turn lamp on or off.
        """
        self._enabled = enabled
        self._iotool.execute(*self._iotool.commands.transmitted_lamp(enabled=enabled))
        self._update_property('enabled', enabled)

    def get_enabled(self):
        return self._enabled

    def _update_push_states(self, state, old_state):
        # superclass prevents pushing a state identical to the current one.
        # But for TL_Lamp, this is useful in case something is going to use
        # IOTool to change the intensity behind the scenes and thus wants to
        # push the current intensity/enabled state onto the stack.
        pass


class SutterLED_Lamp(TL_Lamp_Base):
    def __init__(self, iotool, property_server=None, property_prefix=''):
        super().__init__(iotool, property_server, property_prefix)
        self.set_intensity(255)

    def set_intensity(self, value):
        """Set intensity to any value in the range [0, 255] for min to max.
        """
        self._intensity = value
        self._iotool.execute(*self._iotool.commands.transmitted_lamp(intensity=value))
        self._update_property('intensity', value)

    def get_intensity(self):
        return self._intensity


class LeicaLED_Lamp(TL_Lamp_Base):
    def __init__(self, dmi8_tl, iotool, property_server=None, property_prefix=''):
        super().__init__(iotool, property_server, property_prefix)
        self.set_intensity = dmi8_tl.set_lamp_intensity
        self.get_intensity = dmi8_tl.get_lamp_intensity
