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
# Authors: Erik Hvatum, Zach Pincus

import contextlib

from ...messaging import message_device
from ...util import property_device
from . import microscopy_method_names

GET_ALL_METHODS = 70026
GET_ACT_METHOD = 70028
SET_ACT_METHOD = 70029

class DM6000Device(message_device.LeicaAsyncDevice, property_device.PropertyDevice):
    def __init__(self, message_manager, property_server=None, property_prefix=''):
        # init LeicaAsyncDevice last because that calls the subclasses _setup_device() method, which might need
        # access to the property_server etc.
        property_device.PropertyDevice.__init__(self, property_server, property_prefix)
        message_device.LeicaAsyncDevice.__init__(self, message_manager)
        self._state_stack = []

    def _set_state(self, **state):
        """Set a number of device parameters at once using keyword arguments, e.g.
        device.set_state(async=False, x=10)"""
        for k, v in state.items():
            getattr(self, 'set_'+k)(v)

    def push_state(self, **state):
        """Set a number of device parameters at once using keyword arguments, while
        saving the old values of those parameters. pop_state() will restore those
        previous values. push_state/pop_state pairs can be nested arbitrarily.

        If the device is in async mode, wait for the state to be set before
        proceeding.
        """
        old_state = {k: getattr(self, 'get_'+k)() for k in state.keys()}
        self._state_stack.append(old_state)
        # set async mode first for predictable results
        async = state.pop('async', None)
        if async is not None:
            self.set_async(async)
        self._set_state(**state)
        self.wait() # no-op if not in async, otherwise wait for all setting to be done.

    def pop_state(self):
        """Restore the most recent set of device parameters changed by a push_state()
        call.

        If the device is in async mode, wait for the state to be restored before
        proceeding.
        """
        old_state = self._state_stack.pop()
        async = old_state.pop('async', None)
        self._set_state(**old_state)
        # unset async mode last for predictable results
        if async is not None:
            self.set_async(async)
        self.wait() # no-op if not in async, otherwise wait for all setting to be done.

    @contextlib.contextmanager
    def _pushed_state(self, **state):
        """context manager to push and pop state around a with-block"""
        self.push_state(**state)
        try:
            yield
        finally:
            self.pop_state()


class Stand(DM6000Device):
    def get_all_microscopy_methods(self):
        """Returns a dict of microscopy method names to bool values indicating whether the associated
        microscopy method is available."""
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
