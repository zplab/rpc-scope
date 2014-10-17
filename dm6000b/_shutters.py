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
# Authors: Erik Hvatum


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

class _Shutters:
    '''A mix-in for IL and TL providing shutter control functions used by both.'''
    def _get_shutters(self):
        is_open = [int(s) for s in self.send_message(GET_SHUTTER_LAMP, async=False, intent="get shutter openedness").response.split(' ')]

        errors = []
        if is_open[0] == -1:
            errors.append('Scope reports that TL shutter is in a bad state.')
        if is_open[1] == -1:
            errors.append('Scope reports that IL shutter is in a bad state.')

        if errors:
            raise RuntimeError('  '.join(errors))

        return bool(is_open[0]), bool(is_open[1])

    def _set_shutter(self, shutter_idx, is_open):
        if type(is_open) is bool:
            is_open = int(is_open)
        response = self.send_message(SET_SHUTTER_LAMP, shutter_idx, is_open, async=False, intent="set shutter openedness")
