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

from .. import messaging
from . import microscopy_method_names

GET_ALL_METHODS = 70026
GET_ACT_METHOD = 70028
SET_ACT_METHOD = 70029

class DM6000Device(messaging.message_device.LeicaAsyncDevice):
    def __init__(self, message_manager, property_server=None, property_prefix=''):
        super().__init__(message_manager)
        self._property_server = property_server
        self._property_prefix = property_prefix

    def _add_property(self, name, value):
        if self._property_server:
            return self._property_server.add_property(self._property_prefix+name, value)
        else:
            return lambda x: None
            
class Stand(DM6000Device):
    def get_all_microscopy_methods(self):
        '''Returns a dict of microscopy method names to bool values indicating whether the associated
        microscopy method is available.'''
        method_mask = list(self.send_message(GET_ALL_METHODS, async=False, intent='get mask of available microscopy methods').response.strip())
        method_mask.reverse()
        method_dict = {}
        for method, is_available in zip(microscopy_method_names.NAMES, list(method_mask)):
            method_dict[method] = bool(int(is_available))
        return method_dict

    def get_available_microscopy_methods(self):
        available_methods = [name for name, is_available in self.get_all_microscopy_methods().items() if is_available]
        available_methods.sort()
        return available_methods

    def get_active_microscopy_method(self):
        method_idx = int(self.send_message(GET_ACT_METHOD, async=False, intent='get name of currently active microscopy method').response)
        return microscopy_method_names.NAMES[method_idx]

    def set_active_microscopy_method(self, microscopy_method_name):
        if microscopy_method_name not in microscopy_method_names.NAMES_TO_INDICES:
            raise KeyError('Value specified for microscopy method name must be one of {}.'.format(self.get_available_microscopy_methods()))
        response = self.send_message(SET_ACT_METHOD, microscopy_method_names.NAMES_TO_INDICES[microscopy_method_name], intent='switch microscopy methods')
