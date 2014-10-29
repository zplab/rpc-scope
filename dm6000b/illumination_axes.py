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
from rpc_acquisition.enumerated_properties import DictProperty


# 77032 is an unusual command in that two outstanding instances issued with
# different values for their first parameter are answered separately.
# Furthermore, the response does not include any parameters, making it difficult
# (if responses are always received in order) or impossible (if they are not)
# to match response to command without retaining state information and requested
# changes to that state.  If such information were kept, a failure could then be
# resolved to a specific request by comparing expected post-condition and actual
# post-condition.
# However, by not coalescing the messages, we are at least guaranteed to be able
# to wait for the same number of responses as messages sent, even if we can't
# match up the precise message and responses. This should be good enough.
SET_SHUTTER_LAMP = 77032
GET_SHUTTER_LAMP = 77033

POS_ABS_IL_TURRET = 78022
GET_POS_IL_TURRET = 78023
GET_CUBENAME = 78027
GET_MIN_POS_IL_TURRET = 78031
GET_MAX_POS_IL_TURRET = 78032

POS_ABS_KOND = 81022
GET_POS_KOND = 81023

class FilterCube(DictProperty):
    def __init__(self, il):
        self._il = il
        super().__init__()

    def get_value(self):
        hw_value = self._read()
        return None if hw_value == 0 else self._hw_to_usr[hw_value]

    def _get_hw_to_usr(self):
        min_pos = int(self._il.send_message(GET_MIN_POS_IL_TURRET, async=False, intent="get IL turret minimum position").response)
        max_pos = int(self._il.send_message(GET_MAX_POS_IL_TURRET, async=False, intent="get IL turret maximum position").response)
        # NB: All positions in our filter cube turret are occupied and the manual does not describe the response to
        # a name query for an empty position.  I assume that it is "-" or "", but this assumption may require correction
        # if we ever do come to have an empty position.
        d = {}
        for idx in range(min_pos, max_pos+1):
            name = self._il.send_message(GET_CUBENAME, idx, async=False, intent="get filter cube name").response[1:].strip()
            if len(name) != 0 and name != '-':
                d[idx] = name
        return d

    def _read(self):
        return int(self._il.send_message(GET_POS_IL_TURRET, async=False, intent="get filter turret position").response.split(' ')[0])

    def _write(self, value):
        response = self._il.send_message(POS_ABS_IL_TURRET, value, intent="set filter turret position")

class _ShutterDevice(message_device.LeicaAsyncDevice):
    def get_shutter_open(self):
        '''True: shutter open, False: shutter closed.'''
        shutter_open = self.send_message(GET_SHUTTER_LAMP, async=False, intent="get shutter openedness").response.split(' ')[self._shutter_idx]
        shutter_open = int(shutter_open)
        if shutter_open == -1:
            raise RuntimeError('Shutter is in an invalid state.')
        return bool(shutter_open)

    def set_shutter_open(self, shutter_open):
        response = self.send_message(SET_SHUTTER_LAMP, self._shutter_idx, int(shutter_open), coalesce=False, intent="set shutter openedness")

class IL(_ShutterDevice):
    '''IL represents an interface into elements used in Incident Light (Fluorescence) mode.'''
    _shutter_idx = 1
    # TODO: add filter cube position control, DIC fine shearing, IL aperture control (size 0-6 or whatever / circle vs. square),
    # and lumencor control, both as a 'lumencor' instance variable of a lumencor-controlling class,
    # and as one or two convenience functions exposed at this level -- probably something that like 
    # enable_lamps(uv=None, teal=None [...]), and lamp_power(uv=None [...]), where you can control
    # all lamps at once. ('None' would mean don't change the state of that lamp).
    def _setup_device(self):
        self.filter_cube = FilterCube(self)

class TL(_ShutterDevice):
    '''IL represents an interface into elements used in Transmitted Light (Brighftield and DIC) mode.'''
    _shutter_idx = 0
    def get_condenser_retracted(self):
        '''True: condenser head is deployed, False: condenser head is retracted.'''
        deployed = int(self.send_message(GET_POS_KOND, async=False, intent="get condenser position").response)
        if deployed == 2:
            raise RuntimeError('The condenser head is in an invalid state.')
        return not bool(deployed)

    def set_condenser_retracted(self, retracted):
        response = self.send_message(POS_ABS_KOND, int(not retracted), intent="set condenser position")

    # TODO: add control over field and aperture diaphragms and transmitted LED enable and power.
