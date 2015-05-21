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

import contextlib

@contextlib.contextmanager
def pushed_state(device, **state):
    """context manager to push and pop state around a with-block"""
    device.push_state(**state)
    try:
        yield
    finally:
        device.pop_state()

class StateStackDevice:
    def __init__(self):
        self._state_stack = []

    def _set_state(self, **state):
        """Set a number of device parameters at once using keyword arguments, e.g.
        device.set_state(foo=False, bar=10)"""
        for k, v in state.items():
            getattr(self, 'set_'+k)(v)

    def push_state(self, **state):
        """Set a number of device parameters at once using keyword arguments, while
        saving the old values of those parameters. pop_state() will restore those
        previous values. push_state/pop_state pairs can be nested arbitrarily.
        """
        old_state = {k: getattr(self, 'get_'+k)() for k in state.keys()}
        self._state_stack.append(old_state)
        self._set_state(**state)

    def pop_state(self):
        """Restore the most recent set of device parameters changed by a push_state()
        call.
        """
        old_state = self._state_stack.pop()
        self._set_state(**old_state)
