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

class TablePosTable(Qt.QWidget):
    def __init__(
            self,
            scope, scope_properties,
            positions=(),
            window_title='Table Positions Table',
            parent=None):
        super().__init__(parent)
        self.setWindowTitle(window_title)
        self.model = PosTableModel(('x', 'y', 'z'), om.SignalingList(), self)
        self.view = PosTableView(self.model, self)
        self.setLayout(Qt.QVBoxLayout())
        self.layout().addWidget(self.view)

    def store_current_position(self):
        self.positions_signaling_list.append(Pos(*self.scope.stage.position))

    @property
    def positions_signaling_list(self):
        return self.pos_table_widget.model.signaling_list

    @positions_signaling_list.setter
    def positions_signaling_list(self, v):
        self.pos_table_widget.model.signaling_list = v

    @property
    def positions(self):
        return [(e.x, e.y, e.z) for e in self.positions_signaling_list]

    @positions.setter
    def positions(self, v):
        self.positions_signaling_list = om.SignalingList(Pos(*e) for e in v)

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

    def __init__(self, x=None, y=None, z=None, parent=None):
        super().__init__(parent)
        for property in self.properties:
            property.instantiate(self)
        self.x, self.y, self.z = x, y, z

    properties = []

    def component_default_value_callback(self):
        pass

    def take_component_arg_callback(self, v):
        if v is not None:
            return float(v)

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

    for property in properties:
        exec(property.changed_signal_name + ' = Qt.pyqtSignal(object)')
    del property