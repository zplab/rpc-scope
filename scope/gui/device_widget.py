# The MIT License (MIT)
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
# Authors: Erik Hvatum <ice.rikh@gmail.com>, Zach Pincus <zpincus@wustl.edu>

from PyQt5 import Qt
import collections
from ..simple_rpc import rpc_client

def has_component(scope, component):
    property_path = component.strip('.').split('.')[1:] # skip the leading 'scope.'
    container = scope
    try:
        for element in property_path:
            container = getattr(container, element)
    except AttributeError:
        return False
    else:
        return True

class DeviceWidget(Qt.QWidget):
    _PropertyChangeSignal = Qt.pyqtSignal(str, object)

    @classmethod
    def can_run(cls, scope):
        """Report on whether the current scope object supports a given widget."""
        return has_component(scope, cls.PROPERTY_ROOT)

    def __init__(self, scope, scope_properties, parent):
        super().__init__(parent)
        self.setAttribute(Qt.Qt.WA_DeleteOnClose, True)
        self.rpc_client = scope._rpc_client
        self.rpc_functions = scope._functions_proxied
        self.scope_properties = scope_properties
        self._subscribed_properties = collections.defaultdict(set)
        # It is not safe to manipulate Qt widgets from another thread, and our property change callbacks
        # are executed by the property client thread.  It is safe to emit a signal from a non-Qt thread,
        # so long as any connections to that signal are established explicitly as queued connections.
        # (Qt.Qt.AutomaticConnection connections automatically enter cross-thread (queued) mode ONLY
        # when the thread in question is a Qt thread, so we need to use the explicit queued connection.)
        self._PropertyChangeSignal.connect(self._property_changed, Qt.Qt.QueuedConnection)

    def closeEvent(self, event):
        for property in self._subscribed_properties:
            self.scope_properties.unsubscribe(property, self._emit_property_changed)
        event.accept()

    def _emit_property_changed(self, property, value):
        # need to wrap the emit in a method, because each time emit is accessed, it is a new
        # object, but each time methods are accessed, we get the same object. This is important
        # because the property_client unsubscribes based on object identity.
        self._PropertyChangeSignal.emit(property, value)

    def _property_changed(self, property, value):
        for handler in self._subscribed_properties[property]:
            handler.handle_update(value)

    def _get_property_setter(self, property):
        scope, *device_path, property_name = property.split('.')
        # all property names start with 'scope.', but the rpc server doesn't "see" the top-most namespace.
        property_setter = '.'.join(device_path) + '.set_' + property_name
        if property_setter in self.rpc_functions:
            return self.rpc_client.proxy_function(property_setter)
        else:
            return None

    def is_property_readonly(self, property):
        return self._get_property_setter(property) is None

    def subscribe(self, property, callback):
        """Register a callback to be updated with new values for a given property.

        If the property is writable, this function returns an "update" function to
        call to provide new property values. Otherwise None is returned.
        """
        rpc_updater = self._get_property_setter(property)
        handler = _PropertyHandler(rpc_updater, callback)
        self.scope_properties.subscribe(property, self._emit_property_changed)
        self._subscribed_properties[property].add(handler)
        if rpc_updater is not None:
            return handler.update_device_if_needed

class _PropertyHandler:
    def __init__(self, rpc_updater, callback):
        self.rpc_updater = rpc_updater
        self.callback = callback
        self.value = None

    def handle_update(self, value):
        self.value = value
        self.callback(value)

    def update_device_if_needed(self, value):
        if self.rpc_updater is None:
            raise TypeError('Property is not writable!')
        if value != self.value: # no cyclic updates, thankyouverymuch
            try:
                self.rpc_updater(value)
            except rpc_client.RPCError:
                self.handle_update(self.value) # tell the GUI that the old value is still correct
                raise
            self.value = value
