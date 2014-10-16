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

SET_SHUTTER_LAMP = 77032
GET_SHUTTER_LAMP = 77033

class Lamp(message_device.LeicaAsyncDevice):
    def set_shutters_opened(self, tl_il):
        '''Set TL and IL opened states to respective elements of tl_il tuple/iterable.'''
        tl, il = tl_il
        self.set_tl_shutter_opened(tl)
        self.set_il_shutter_opened(il)

    def _set_shutter_opened(self, shutter_idx, opened):
        if type(opened) is bool:
            opened = int(opened)
        response = self.send_message(SET_SHUTTER_LAMP, shutter_idx, opened, intent="set shutter openedness")

    def set_tl_shutter_opened(self, opened):
        self._set_shutter_opened(0, opened)

    def set_il_shutter_opened(self, opened):
        self._set_shutter_opened(1, opened)

    def get_shutters_opened(self):
        opened = [int(s) for s in self.send_message(GET_SHUTTER_LAMP, async=False, intent="get shutter openedness").response.split(' ')]

        errors = []
        if opened[0] == -1:
            errors.append('Scope reports that TL shutter is in a bad state.')
        if opened[1] == -1:
            errors.append('Scope reports that IL shutter is in a bad state.')

        if errors:
            raise RuntimeError('  '.join(errors))

        return bool(opened[0]), bool(opened[1])

    def get_tl_shutter_opened(self):
        return self.get_shutters_opened()[0]

    def get_il_shutter_opened(self):
        return self.get_shutters_opened()[1]
