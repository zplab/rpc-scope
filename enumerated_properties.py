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

# Base classes capable of being made available through RPC for properties limited to
# predetermined or run-time determined sets of valid values.

class ReadonlySetProperty:
    '''Base class for any enumerated device property that is limited to a set of known values
    typically retrieved from and passed to the hardware as is.

    A hypothetical example of such a property: a mirror in a beam path has a filter magazine
    from which one filter may be deployed at a time.  The mirror controller has a simple
    serial interface protocol permitting reading of the names of the filters in the magazine,
    deployment of a filter identified by name, and retrieval of the name of the currently
    deployed filter.  The same strings by which the user identifies filters are recognized
    by the mirror controller hardware itself.'''

    def __init__(self):
        self._valid_set = self._get_valid_set()

    def get_recognized_values(self):
        '''The list of recognized values that may be assumed by .value, and in the case
        of a read/write attribute, assigned to .value.  Assigning anything not appearing
        in this list to a writeable attribute's .value causes a ValueError exception to
        be raised.'''
        return sorted(list(self._valid_set))

    def get_value(self):
        '''The current value.'''
        return self._read()

    def _get_valid_set(self):
        raise NotImplementedError()

    def _read(self):
        raise AttributeError("can't get attribute")


class SetProperty(ReadonlySetProperty):
    __doc__ = ReadonlySetProperty.__doc__
    
    def set_value(self, value):
        if value not in self._valid_set:
            raise ValueError('value must be one of {}.'.format(self.get_recognized_values()))
        self._write(value)

    def _write(self, value):
        raise AttributeError("can't set attribute")




class ReadonlyDictProperty:
    '''Base class for any enumerated device property that is limited to a set of non-user-
    friendly values identified to the user by more meaningful names.

    A hypothetical example of such a property: a mirror in a beam path has a filter magazine
    from which one filter may be deployed at a time.  The mirror controller has a simple
    serial interface protocol permitting reading of the names of the filters in the magazine
    as an ordered list.  The 0-based index of each element is used in the filter change
    request command to identify the filter that should be deployed and is contained in the
    reply to a currently deployed filter query.  The strings by which the user identifies
    filters are translated to/from integer values recognized by the mirror controller
    hardware.'''

    def __init__(self):
        self._hw_to_usr = self._get_hw_to_usr()
        self._usr_to_hw = {usr : hw for hw, usr in self._hw_to_usr.items()}

    def get_recognized_values(self):
        '''The list of recognized values that may be assumed by .value, and in the case
        of a read/write attribute, assigned to .value.  Assigning anything not appearing
        in this list to a writeable attribute's .value causes a ValueError exception to
        be raised.'''
        return sorted(list(self._usr_to_hw.keys()))

    def get_value(self):
        '''The current value.'''
        return self._hw_to_usr[self._read()]

    def _get_hw_to_usr(self):
        raise NotImplementedError()

    def _read(self):
        raise AttributeError("can't get attribute")

class DictProperty(ReadonlyDictProperty):
    __doc__ = ReadonlyDictProperty.__doc__
    
    def set_value(self, value):
        if value not in self._usr_to_hw:
            raise ValueError('value must be one of {}.'.format(self.get_recognized_values()))
        self._write(self._usr_to_hw[value])

    def _write(self, value):
        raise AttributeError("can't set attribute")
