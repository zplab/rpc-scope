# This code is licensed under the MIT License (see LICENSE file for details)

from . import state_stack

class PropertyDevice(state_stack.StateStackDevice):
    """A base class that provides convenience methods for microscope
    device classes that want to present a few properties to the server."""

    def __init__(self, property_server, property_prefix):
        """property_server is the property server instance to send property
        updates to. It is expected that property_server may be None if no
        property updates should be made. property_prefix will be prepended to
        the name of any property updates provided."""
        super().__init__()
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
