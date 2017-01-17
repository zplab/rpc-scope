# The MIT License (MIT)
#
# Copyright (c) 2016 WUSTL ZPLAB
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
import sdl2
from ..client_util import game_controller_input

class _GameControllerInput(game_controller_input.GameControllerInput):
    # define an adapter thread class that's a QThread but works like threading.thread
    class THREAD_TYPE(Qt.QThread):
        def __init__(self, target, parent=None):
            super().__init__(parent)
            self.target = target

        def run(self):
            self.target()

        def join(self):
            self.wait()

# GameControllerInputWidget is actually just a QAction. QAction provides all the functionality required while avoiding
# the need to make and lay out a QPushButton.
class GameControllerInputWidget(Qt.QAction):
    connected_input_removed_signal = Qt.pyqtSignal()

    @staticmethod
    def can_run(scope):
        return hasattr(scope, 'stage')

    def __init__(self, scope, scope_properties, device=-1, parent=None):
        """If -1 (the default) is supplied for device_id, GameControllerInputWidget attempts to use the gamepad/joystick with
        the lowest ID if on one is available, displays a device selection dialog if multiple are available, and remains
        in the disconnected state if none are available.  Supplying None for device_id results in the
        gamepad/joystick with the lowest ID being used if only one device is available, an error messagebox being
        displayed if there are no devices available, and a device selection dialog being displayed if multiple devices
        are available.  Supplying any other value connects to the specified gamepad/joystick and displays an error
        messagebox if this fails.

        If connect is called while already connected, the existing connection is closed, and a new connection is
        made following the rules described above."""
        super().__init__(parent)
        self.scope = scope
        self.game_controller_input = None
        self.setText('Connect Game Controller')
        Qt.QApplication.instance().aboutToQuit.connect(self.disconnect)
        self.connected_input_removed_signal.connect(self.on_connected_input_removed_signal)
        self.triggered.connect(self.on_triggered)
        self.connect(device)

    def connect_game_controller(self, device):
        self.game_controller_input = _GameControllerInput(self.scope, device)
        self.game_controller_input.handle_device_removed = self.connected_input_removed_signal.emit
        self.game_controller_input.make_and_start_event_loop_thread()

    def on_connected_input_removed_signal(self):
        self.disconnect()

    @property
    def is_connected(self):
        return self.game_controller_input is not None

    def on_triggered(self):
        if self.is_connected:
            self.disconnect()
        else:
            self.connect(device=None)

    def connect(self, device=-1):
        self.disconnect()
        if device in (-1, None):
            devices = game_controller_input.enumerate_devices()
            if len(devices) == 0:
                if device is None:
                    m = "No game controllers are available. (Newly plugged-in controllers do not become available until Python is restarted.)"
                    Qt.QMessageBox.warning(None, "Error", m)
                return
            elif len(devices) == 1:
                self.connect_game_controller(0)
            else:
                dlg = _GameControllerDeviceSelectionDialog(devices)
                if dlg.exec() == Qt.QDialog.Accepted and dlg.selected_device is not None:
                    device_id = dlg.selected_row
                    self.connect_game_controller(device_id)
                else:
                    return
        else:
            self.connect_game_controller(device)
        self.setText('Disconnect Game Controller')
        self.setToolTip('Currently connected to "{}".'.format(self.game_controller_input.device_name))

    def disconnect(self):
        if not self.is_connected:
            return
        self.game_controller_input.stop_and_destroy_event_loop_thread()
        self.game_controller_input = None
        self.setText('Connect Game Controller')
        self.setToolTip(None)

class _GameControllerDeviceSelectionDialog(Qt.QDialog):
    def __init__(self, devices, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowModality(Qt.Qt.WindowModal)
        self.setWindowTitle('Select Game Controller')
        self.setSizeGripEnabled(True)
        self.resize(865, 400)
        self.button_box = Qt.QDialogButtonBox(Qt.QDialogButtonBox.Ok | Qt.QDialogButtonBox.Cancel, Qt.Qt.Horizontal)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.connect_button = self.button_box.button(Qt.QDialogButtonBox.Ok)
        self.connect_button.setText('Connect')
        l = Qt.QVBoxLayout()
        self.setLayout(l)
        self.table_widget = Qt.QTableWidget()
        self.table_widget.setEditTriggers(Qt.QAbstractItemView.NoEditTriggers)
        self.table_widget.setSelectionMode(Qt.QAbstractItemView.SingleSelection)
        self.table_widget.setSelectionBehavior(Qt.QAbstractItemView.SelectRows)
        self.table_widget.setDragDropMode(Qt.QAbstractItemView.NoDragDrop)
        self.table_widget.setColumnCount(2)
        self.table_widget.setHorizontalHeaderItem(0, Qt.QTableWidgetItem('Type'))
        self.table_widget.setHorizontalHeaderItem(1, Qt.QTableWidgetItem('Name'))
        l.addWidget(self.table_widget)
        l.addWidget(self.button_box)
        sm = self.table_widget.selectionModel()
        sm.currentRowChanged.connect(self.on_table_widget_current_row_changed)
        self.selected_row = None
        self.table_widget.setRowCount(len(self.devices))
        sm.clear()
        for i, (device_type, device_name) in enumerate(devices):
            self.table_widget.setItem(i, 0, Qt.QTableWidgetItem(device_type))
            self.table_widget.setItem(i, 1, Qt.QTableWidgetItem(device_name))
        if self.device_rows:
            self.table_widget.resizeColumnsToContents()
            sm.select(sm.model().index(0,0), sm.Rows | sm.Current | sm.Select)

    def on_table_widget_current_row_changed(self, midx, old_midx):
        if midx.isValid():
            self.connect_button.setEnabled(True)
            self.selected_row = midx.row()
        else:
            self.connect_button.setEnabled(False)
            self.selected_row = None