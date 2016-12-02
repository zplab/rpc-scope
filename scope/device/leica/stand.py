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
from ...messaging import message_manager
from ...util import property_device
from ...util import smart_serial
from ...config import scope_configuration
from . import microscopy_method_names

GET_MODUL_TYPE = 70001
GET_ALL_METHODS = 70026
GET_ACT_METHOD = 70028
SET_ACT_METHOD = 70029
SET_STAND_EVENT_SUBSCRIPTIONS = 70003

class Stand(message_device.LeicaAsyncDevice, property_device.PropertyDevice):
    _DESCRIPTION = 'Leica microscope'
    _EXPECTED_INIT_ERRORS = (smart_serial.SerialException,)

    def __init__(self, property_server=None, property_prefix=''):
        property_device.PropertyDevice.__init__(self, property_server, property_prefix)
        config = scope_configuration.get_config()
        manager = message_manager.LeicaMessageManager(config.stand.SERIAL_PORT, config.stand.SERIAL_ARGS, daemon=True)
        message_device.LeicaAsyncDevice.__init__(self, manager)

    def _setup_device(self):
        # If we're talking to a DMi8 that has not received a command since being attached, its first reply contains a leading null byte.  So, we provoke
        # this reply by issuing an empty command (a carriage return), knowing that we will receive one of two replies: a '99999' or a '\099999'.  Receiving
        # one removes the expectation of receiving the other.
        self._message_manager.pending_standalone_responses['9999'].append(lambda response: self._message_manager.pending_standalone_responses.pop('\0999'))
        self._message_manager.pending_standalone_responses['\0999'].append(lambda response: self._message_manager.pending_standalone_responses.pop('9999'))
        self._message_manager._send_message('\r')
        self.send_message(SET_STAND_EVENT_SUBSCRIPTIONS, 1, 0, 0, 0, 0, 0, 0, 0, async=False, intent="subscribe to stand method change events")
        self.register_event_callback(GET_ACT_METHOD, self._on_method_event)
        r = self.send_message(GET_MODUL_TYPE, async=False, intent="get master model name and list of available function unit IDs").response.split(' ')
        self._model_name = r[0]
        self._available_function_unit_IDs = set(int(rv) for rv in r[1:])

    def get_model_name(self):
        return self._model_name

    def get_available_function_unit_IDs(self):
        return self._available_function_unit_IDs

    def _on_method_event(self, response):
        self._update_property('active_microscopy_method', microscopy_method_names.NAMES[int(response.response)])

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

class LeicaComponent(message_device.LeicaAsyncDevice, property_device.PropertyDevice):
    def __init__(self, stand: Stand, property_server=None, property_prefix=''):
        # init LeicaAsyncDevice last because that calls the subclasses _setup_device() method, which might need
        # access to the property_server etc.
        property_device.PropertyDevice.__init__(self, property_server, property_prefix)
        message_device.LeicaAsyncDevice.__init__(self, stand._message_manager)

    # set async first when pushing, revert async last when popping
    def _get_push_weights(self, state):
        return {'async':-1}

    def _get_pop_weights(self, state):
        return {'async':1}

    def push_state(self, **state):
        """Set a number of device parameters at once using keyword arguments, while
        saving the old values of those parameters. pop_state() will restore those
        previous values. push_state/pop_state pairs can be nested arbitrarily.

        If the device is in async mode, wait for the state to be set before
        proceeding.
        """
        super().push_state(**state)
        self.wait() # no-op if not in async, otherwise wait for all setting to be done.

    def pop_state(self):
        """Restore the most recent set of device parameters changed by a push_state()
        call.

        If the device is in async mode, wait for the state to be restored before
        proceeding.
        """
        super().pop_state()
        self.wait() # no-op if not in async, otherwise wait for all setting to be done.

