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
# changes to that state.  If such information were kept, a failure may then be
# resolved to a specific request by comparing expected post-state and actual
# post-state.
SET_SHUTTER_LAMP = 77032
GET_SHUTTER_LAMP = 77033

class Shutters(message_device.LeicaAsyncDevice):
    '''Leica refers to this function unit (77) as 'Lamp'.  Function unit 77 is also provides direct control
    of 'lamp intensity', which in the case of ZPLAB is always set to 255 (maximum) by setting all objective
    intensity parameters to 255, such that when objective is changed, intensity reverts to 255.  This is done
    because ZPLAB uses LED illumination and DM6000B lamp support is intended for halogen bulbs.  As such,
    the DM6000B TL light path includes a variable filter intended to normalize halogen output, the spectra
    of which vary with intensity.  The least attenuation of green LED TL illumination is seen with the
    variable filter in the maximum intensity position.'''
    def get_il_tl(self):
        '''Open/close TL and IL shutters according to elements of tl_il tuple/iterable.  Note that setting
        this property is not entirely asynchronous - it always blocks until the requested TL shutter
        state change has occurred.'''
        opened = [int(s) for s in self.send_message(GET_SHUTTER_LAMP, async=False, intent="get shutter openedness").response.split(' ')]

        errors = []
        if opened[0] == -1:
            errors.append('Scope reports that TL shutter is in a bad state.')
        if opened[1] == -1:
            errors.append('Scope reports that IL shutter is in a bad state.')

        if errors:
            raise RuntimeError('  '.join(errors))

        return bool(opened[0]), bool(opened[1])

    def get_tl(self):
        '''True: TL shutter open, False: TL shutter closed.  Note that setting this property is always a synchronous operation.'''
        return self.get_il_tl()[0]

    def get_il(self):
        '''True: IL shutter open, False: IL shutter closed.  Note that setting this property is always a synchronous operation.'''
        return self.get_il_tl()[1]

    def set_tl_il(self, tl_il):
        tl, il = tl_il
        self._set_shutter_opened(0, tl, False)
        self._set_shutter_opened(1, il, None)

    def _set_shutter_opened(self, shutter_idx, opened, async):
        if type(opened) is bool:
            opened = int(opened)
        response = self.send_message(SET_SHUTTER_LAMP, shutter_idx, opened, async=async, intent="set shutter openedness")

    def set_tl(self, opened):
        self._set_shutter_opened(0, opened, False)

    def set_il(self, opened):
        self._set_shutter_opened(1, opened, False)
