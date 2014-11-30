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
# Authors: Zach Pincus

class PropertyDevice:
    """A base class that provides convenience methods for microscope
    device classes that want to present a few properties to the server."""
    def __init__(self, property_server, property_prefix):
        """property_server is the property server instance to send property
        updates to. It is expected that property_server may be None if no
        property updates should be made. property_prefix will be prepended to
        the name of any property updates provided."""
        self._property_server = property_server
        self._property_prefix = property_prefix

    def _update_property(self, name, value):
        """If a non-None property_server was provided, update the named property
        on the server to a given value."""
        if self._property_server:
            self._property_server.update_property(self._property_prefix+name, value)

    def _add_property(self, name, initial_value):
        """Return a function that will update the named property with new values.
        The returned update function need only be called as update(new_value), as
        the property name is stored within the update function.
        If no property server was provided, return a function that can be called
        but has no effect."""
        if self._property_server:
            return self._property_server.add_property(self._property_prefix+name, initial_value)
        else:
            return lambda value: None
