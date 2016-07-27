# The MIT License (MIT)
#
# Copyright (c) 2015 WUSTL ZPLAB
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

import json
from PyQt5 import Qt
from ris_widget import om

class StagePosTableWidget(Qt.QWidget):
    @classmethod
    def can_run(cls, scope):
        try:
            x, y, z = (float(c) for c in scope.stage.position)
        except:
            return False
        return True

    def __init__(
            self,
            host, scope, scope_properties,
            positions=(),
            window_title='Stage Position Table',
            parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.Qt.WA_DeleteOnClose, True)
        self.scope = scope
        self.scope_properties = scope_properties
        self.setWindowTitle(window_title)
        self.model = PosTableModel(
            ('x', 'y', 'z', 'info'),
            positions if isinstance(positions, om.SignalingList) else om.SignalingList(Pos(*e) for e in positions),
            self)
        self.view = PosTableView(self.model, self)
        self.setLayout(Qt.QVBoxLayout())
        self.layout().addWidget(self.view)
        self.store_current_stage_position_button = Qt.QPushButton('Store Current Stage Position')
        self.store_current_stage_position_button.clicked.connect(self.store_current_stage_position)
        self.layout().addWidget(self.store_current_stage_position_button)
        self.move_to_focused_stage_position_button = Qt.QPushButton('Move To Selected Position')
        self.move_to_focused_stage_position_button.clicked.connect(self.move_to_focused_stage_position)
        self.layout().addWidget(self.move_to_focused_stage_position_button)
        hlayout = Qt.QHBoxLayout()
        self.export_to_clipboard_button = Qt.QPushButton('Export To Clipboard (JSON)')
        self.export_to_clipboard_button.clicked.connect(self.export_to_clipboard)
        hlayout.addWidget(self.export_to_clipboard_button)
        self.import_from_clipboard_button = Qt.QPushButton('Import From Clipboard (JSON)')
        self.import_from_clipboard_button.clicked.connect(self.import_from_clipboard)
        hlayout.addWidget(self.import_from_clipboard_button)
        self.layout().addLayout(hlayout)
        self.view.selectionModel().currentRowChanged.connect(self._on_stage_position_focus_changed)
        self._on_stage_position_focus_changed(self.view.selectionModel().currentIndex(), None)

    def store_current_stage_position(self):
        self.positions_signaling_list.append(Pos(*self.scope.stage.position))

    def move_to_focused_stage_position(self):
        midx = self.view.selectionModel().currentIndex()
        if midx.isValid():
            try:
                self.scope.stage.push_state(async=False)
                pos = self.positions_signaling_list[midx.row()]
                self.scope.stage.position = pos.x, pos.y, pos.z
            except Exception as e:
                Qt.QMessageBox.warning(self, 'Command Failed', 'Could not move stage to selected position ({}).'.format(e))

    def export_to_clipboard(self):
        Qt.QApplication.clipboard().setText(json.dumps(self.positions, indent=2))

    def import_from_clipboard(self):
        try:
            positions = [Pos(*e) for e in json.loads(Qt.QApplication.clipboard().text())]
        except Exception as e:
            Qt.QMessageBox.warning(self, 'Bad Data', 'Failed to import positions from clipboard ({}).'.format(e))
        self.positions = positions

    @property
    def positions_signaling_list(self):
        return self.model.signaling_list

    @positions_signaling_list.setter
    def positions_signaling_list(self, v):
        self.model.signaling_list = v

    @property
    def positions(self):
        return [(e.x, e.y, e.z, e.info) for e in self.positions_signaling_list]

    @positions.setter
    def positions(self, v):
        self.positions_signaling_list[:] = [e if isinstance(e, Pos) else Pos(*e) for e in v]

    def _on_stage_position_focus_changed(self, midx, old_midx):
        self.move_to_focused_stage_position_button.setEnabled(midx.isValid())

    def closeEvent(self, event):
        if self.positions:
            print('POSITIONS:')
            print(json.dumps(self.positions, indent=2))
        super().closeEvent(event)

class PosTableView(Qt.QTableView):
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.horizontalHeader().setSectionResizeMode(Qt.QHeaderView.ResizeToContents)
        self.setDragDropOverwriteMode(False)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(Qt.QAbstractItemView.InternalMove)
        self.setDropIndicatorShown(True)
        self.setSelectionBehavior(Qt.QAbstractItemView.SelectRows)
        self.setSelectionMode(Qt.QAbstractItemView.SingleSelection)
        self.delete_current_row_action = Qt.QAction(self)
        self.delete_current_row_action.setText('Delete current row')
        self.delete_current_row_action.triggered.connect(self._on_delete_current_row_action_triggered)
        self.delete_current_row_action.setShortcut(Qt.Qt.Key_Delete)
        self.delete_current_row_action.setShortcutContext(Qt.Qt.WidgetShortcut)
        self.addAction(self.delete_current_row_action)
        self.setModel(model)

    def _on_delete_current_row_action_triggered(self):
        sm = self.selectionModel()
        m = self.model()
        if None in (m, sm):
            return
        midx = sm.currentIndex()
        if midx.isValid():
            m.removeRow(midx.row())

class PosTableModel(om.signaling_list.DragDropModelBehavior, om.signaling_list.PropertyTableModel):
    pass

class Pos(Qt.QObject):
    changed = Qt.pyqtSignal(object)

    def __init__(self, x=None, y=None, z=None, info='', parent=None):
        super().__init__(parent)
        for property in self.properties:
            property.instantiate(self)
        self.x, self.y, self.z, self.info = x, y, z, info

    properties = []

    def component_default_value_callback(self):
        pass

    def take_component_arg_callback(self, v):
        if v is not None:
            return float(v)

    def info_default_value_callback(self):
        return ''

    def take_info_arg_callback(self, v):
        if v is None:
            return ''
        return str(v)

    x = om.Property(
        properties,
        "x",
        default_value_callback=component_default_value_callback,
        take_arg_callback=take_component_arg_callback)

    y = om.Property(
        properties,
        "y",
        default_value_callback=component_default_value_callback,
        take_arg_callback=take_component_arg_callback)

    z = om.Property(
        properties,
        "z",
        default_value_callback=component_default_value_callback,
        take_arg_callback=take_component_arg_callback)

    info = om.Property(
        properties,
        "info",
        default_value_callback=info_default_value_callback,
        take_arg_callback=take_info_arg_callback)

    for property in properties:
        exec(property.changed_signal_name + ' = Qt.pyqtSignal(object)')
    del property