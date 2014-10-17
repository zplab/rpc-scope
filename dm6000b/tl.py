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

# 77032 is an unusual command in that two outstanding instances issued with
# different values for their first parameter are answered separately.
# Furthermore, the response does not include any parameters, making it difficult
# (if responses are always received in order) or impossible (if they are not)
# to match response to command without retaining state information and requested
# changes to that state.  If such information were kept, a failure could then be
# resolved to a specific request by comparing expected post-condition and actual
# post-condition.
SET_SHUTTER_LAMP = 77032
GET_SHUTTER_LAMP = 77033

class TL(message_device.LeicaAsyncDevice):
    '''TL represents an interface into elements of the scope primarily or exclusively
    used in Transmitted Light mode.  Like Stage and unlike ObjectiveTurret, the TL class
    does not represent a single function unit.'''
    def get_condenser_head(self):
        '''True: condenser head is deployed, False: condenser head is retracted.'''
        deployed = int(self.send_message(FLAPPING_GET_POS_KOND, async=False, intent="get flapping condenser position").response)
        if deployed == 2:
            raise RuntimeError('Scope reports that the condenser head, aka the flapping condenser, is in a bad state.')
        return bool(deployed)

    def set_condenser_head(self, deploy):
        if type(deploy) is bool:
            deploy = int(deploy)
        response = self.send_message(FLAPPING_POS_ABS_KOND, deploy, intent="set flapping condenser position")

    def get_shutter(self):
        '''True: TL shutter open, False: TL shutter closed.  Note that setting this property is always a synchronous operation.'''
        is_open = [int(s) for s in self.send_message(GET_SHUTTER_LAMP, async=False, intent="get shutter openedness").response.split(' ')]

        errors = []
        if is_open[0] == -1:
            errors.append('Scope reports that TL shutter is in a bad state.')
        if is_open[1] == -1:
            errors.append('Scope reports that IL shutter is in a bad state.')

        if errors:
            raise RuntimeError('  '.join(errors))

        return bool(is_open[0])

    def set_shutter(self, is_open):
        if type(is_open) is bool:
            is_open = int(is_open)
        response = self.send_message(SET_SHUTTER_LAMP, 0, is_open, async=False, intent="set TL shutter openedness")
