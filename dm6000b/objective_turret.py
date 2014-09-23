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

POS_ABS_OBJ = 76022
GET_POS_OBJ = 76023
SET_IMM_DRY = 76027
GET_IMM_DRY = 76028
GET_OBJPAR = 76033
GET_MIN_POS_OBJ = 76038
GET_MAX_POS_OBJ = 76039

class ObjectiveTurret(message_device.LeicaAsyncDevice):
    '''Note that objective position is reported as 0 when the objective turret is between positions.  The objective
    turret is between positions when it is in the process of responding to a position change request and also when
    manually placed there by physical intervention.'''
    def _setup_device(self):
        minp, maxp = self.get_position_min_max()
        self._mags_to_positions = {}
        for p in range(minp, maxp+1):
            mag = self.send_message(GET_OBJPAR, p, 1).response.split(' ')[2]
            # Note: dm6000b reports magnifications in integer units with a dash indicating no magnification / empty
            # turret position
            mag = None if mag == '-' else int(mag)
            if mag not in self._mags_to_positions:
                self._mags_to_positions[mag] = [p]
            else:
                self._mags_to_positions[mag].append(p)

    def set_position(self, position):
        if position is not None:
            response = self.send_message(POS_ABS_OBJ, position, intent="switch to objective as position {}".format(position))

    def get_position(self):
        return int(self.send_message(GET_POS_OBJ, async=False, intent="get current objective position").response)

    def get_position_min_max(self):
        return (int(self.send_message(GET_MIN_POS_OBJ, async=False, intent="get minimum objective turret position").response),
                int(self.send_message(GET_MAX_POS_OBJ, async=False, intent="get maximum objective turret position").response))

    def set_magnification(self, magnification):
