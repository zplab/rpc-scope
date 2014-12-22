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
# Authors: Erik Hvatum <ice.rikh@gmail.com>

import os
from pathlib import Path
from PyQt5 import Qt, uic

class DeviceWidget(Qt.QWidget):
    # It is not safe to manipulate Qt widgets from another thread, and our property change callbacks
    # are executed by the property client thread.  It is safe to emit a signal from a non-Qt thread,
    # so long as any connections to that signal are established explicitly as queued connections (Qt
    # will fail to recognize the discrepancy in thread affinity for a signal emitted from a thread
    # not running a Qt event loop, preventing Qt.Qt.AutomaticConnection connections from
    # automatically entering cross-thread (queued) mode.
    _ChangeSignalFromPropertyClient = Qt.pyqtSignal(str, object)

    def __init__(self, scope, scope_properties, device_path, py_ui_fpath, parent):
        super().__init__(parent)
        self.setAttribute(Qt.Qt.WA_DeleteOnClose, True)
        self.scope = scope
        self.scope_properties = scope_properties
        self.device_path = device_path
        self.device_path_parts = self.device_path.split('.')
        self.subscribed_prop_paths = set()

        self.device = self
        for p in self.device_path.split('.'):
            self.device = getattr(self.device, p)

        if py_ui_fpath is None:
            # Child class either does not use a .ui file or wants to call uic.loadUiType and such itself
            pass
        else:
            ui_sfpath = str(py_ui_fpath)
            ui_fpath = Path(py_ui_fpath)
            if ui_sfpath.endswith('.py'):
                # Child class is being lazy and gave us its __file__ variable rather than its .ui filename/path
                ui_fpath = ui_fpath.parent / (ui_fpath.parts[-1][:-3] + '.ui')
                ui_sfpath = str(ui_fpath)
            # Note that uic.loadUiType(..) returns a tuple containing two class types (the form class and the Qt base
            # class).  The line below instantiates the form class.  It is assumed that the .ui file resides in the same
            # directory as this .py file.
            self.ui = uic.loadUiType(ui_sfpath)[0]()
            self.ui.setupUi(self)

    def closeEvent(self, event):
        for prop_path in self.subscribed_prop_paths:
            self.scope_properties.unsubscribe(prop_path, self.property_client_property_change_callback, False)
        event.accept()

    def subscribe(self, *prop_path_parts):
        prop_path = '.'.join((self.device_path,) + prop_path_parts)
        self.scope_properties.subscribe(prop_path, self.property_client_property_change_callback, False)
        self.subscribed_prop_paths.add(prop_path)

    def property_client_property_change_callback(self, prop_path, prop_value):
        # Runs in property client thread
        self._ChangeSignalFromPropertyClient.emit(prop_path, prop_value)

    def property_change_slot(self, prop_path, prop_value, is_prop_update=True):
        # Runs in GUI thread
        raise NotImplementedError('pure virtual method called')
