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

import enum
from pathlib import Path
from PyQt5 import Qt
from . import device_widget
from ..simple_rpc import rpc_client
from ..util import state_stack

class PT(enum.Enum):
    Bool = 0,
    Int = 1,
    Enum = 2,
    Objective = 3,
    StageAxisPos = 4

class LimitPixmaps:
    def __init__(self, height):
        dpath = Path(__file__).parent() / 'limit_icons'
        for fname in ('no_limit.svg', 'soft_limit.svg', 'hard_limit.svg', 'hard_and_soft_limit.svg'):
            self._load_pm(dpath / fname)

    def _load_pm(self, fpath):
        

class MicroscopeWidget(device_widget.DeviceWidget):
    PROPERTY_ROOT = 'scope.'
    PROPERTIES = [
#       ('stand.active_microscopy_method', PT.Enum, 'stand.available_microscopy_methods'),
        ('nosepiece.position', PT.Objective, 'nosepiece.all_objectives'),
#       ('nosepiece.safe_mode', PT.Bool),
#       ('nosepiece.immersion_mode', PT.Bool),
        ('il.shutter_open', PT.Bool),
        ('tl.shutter_open', PT.Bool),
        ('il.field_wheel', PT.Enum, 'il.field_wheel_positions'),
        ('il.filter_cube', PT.Enum, 'il.filter_cube_values'),
        # The final element of the 'tl.aperature_diaphragm' tuple, 'scope.nosepiece.position', indicates
        # that 'tl.aperture_diaphragm_range' may change with 'scope.nosepiece.position'.  So,
        # 'tl.aperture_diaphragm_range' should be refreshed upon 'scope.nosepiece.position' change.
        ('tl.aperture_diaphragm', PT.Int, 'tl.aperture_diaphragm_range', 'nosepiece.position'),
        ('tl.field_diaphragm', PT.Int, 'tl.field_diaphragm_range', 'nosepiece.position'),
        ('tl.condenser_retracted', PT.Bool),
        ('stage.xy_fine_manual_control', PT.Bool),
        ('stage.z_fine_manual_control', PT.Bool),
        ('stage.x', PT.StageAxisPos, 'x'),
        ('stage.y', PT.StageAxisPos, 'y'),
        ('stage.z', PT.StageAxisPos, 'z')
    ]

    @classmethod
    def can_run(cls, scope):
        # We're useful if at least one of our properties can be read.  Properties that can not be read
        # when the widget is created are not shown in the GUI.
        for ppath, *_ in cls.PROPERTIES:
            attr = scope
            try:
                for attr_name in ppath.split('.'):
                    attr = getattr(attr, attr_name)
            except:
                continue
            return True
        return False

    def __init__(self, scope, scope_properties, parent=None):
        super().__init__(scope, scope_properties, parent)
        self.load_limit_pixmaps()
        self.setWindowTitle('Microscope')
        self.setLayout(Qt.QGridLayout())
        self.scope = scope
        self.widget_makers = {
            PT.Bool : self.make_bool_widget,
            PT.Int : self.make_int_widget,
            PT.StageAxisPos : self.make_stage_axis_pos_widget,
            PT.Enum : self.make_enum_widget,
            PT.Objective : self.make_objective_widget}
        for ptuple in self.PROPERTIES:
            self.make_widgets_for_property(ptuple)

    def load_limit_pixmaps(self):
        dpath = Path(__file__).parent() / 'limit_icons'
        height = 25
        low_soft_limit_pixmap

    def pattr(self, ppath):
        attr = self.scope
        for attr_name in ppath.split('.'):
            attr = getattr(attr, attr_name)
        return attr

    def make_widgets_for_property(self, ptuple):
#       if ptuple[1] not in (PT.Bool, PT.Enum, PT.Int, PT.Objective):
#           return
        try:
            self.pattr(ptuple[0])
        except:
            Qt.qDebug('Failed to read value of "{}{}", so this property will not be presented in the GUI.'.format(self.PROPERTY_ROOT, ptuple[0]))
            return
        layout = self.layout()
        row = layout.rowCount()
        label = Qt.QLabel(ptuple[0] + ':')
        layout.addWidget(label, row, 0)
        widget = self.widget_makers[ptuple[1]](ptuple)
        layout.addWidget(widget, row, 1)
        return label, widget

    def make_bool_widget(self, ptuple):
        widget = Qt.QCheckBox()
        ppath = self.PROPERTY_ROOT + ptuple[0]
        update = self.subscribe(ppath, callback=widget.setChecked)
        if update is None:
            raise TypeError('{} is not a writable property!'.format(ppath))
        def gui_changed(value):
            try:
                update(value)
            except rpc_client.RPCError as e:
                error = 'Could not set {} ({}).'.format(ppath, e.args[0])
                Qt.QMessageBox.warning(self, 'Invalid Value', error)
        widget.toggled.connect(gui_changed)
        return widget

    def make_int_widget(self, ptuple):
        widget = Qt.QWidget()
        ppath = self.PROPERTY_ROOT + ptuple[0]
        layout = Qt.QHBoxLayout()
        widget.setLayout(layout)
        slider = Qt.QSlider(Qt.Qt.Horizontal)
        slider.setTickInterval(1)
        layout.addWidget(slider)
        spinbox = Qt.QSpinBox()
        layout.addWidget(spinbox)
        handling_change = False
        def prop_changed(value):
            nonlocal handling_change
            if handling_change:
                return
            handling_change = True
            try:
                slider.setValue(value)
                spinbox.setValue(value)
            finally:
                handling_change = False
        def range_changed(_):
            nonlocal handling_change
            if handling_change:
                return
            handling_change = True
            try:
                attr = self.scope
                for attr_name in ptuple[2].split('.'):
                    attr = getattr(attr, attr_name)
                range_ = attr
                slider.setRange(*range_)
                spinbox.setRange(*range_)
            finally:
                handling_change = False
        def gui_changed(value):
            nonlocal handling_change
            if handling_change:
                return
            handling_change = True
            try:
                update(value)
            finally:
                handling_change = False
        update = self.subscribe(ppath, callback=prop_changed)
        if update is None:
            raise TypeError('{} is not a writable property!'.format(ppath))
        self.subscribe(self.PROPERTY_ROOT + ptuple[3], callback=range_changed)
        slider.valueChanged[int].connect(gui_changed)
        spinbox.valueChanged[int].connect(gui_changed)
        return widget

    def make_stage_axis_pos_widget(self, ptuple):
        widget = Qt.QWidget()
        layout = Qt.QHBoxLayout()
        widget.setLayout(layout)
        l_lh, l_ls, e_ls = Qt.QLabel()

    def make_enum_widget(self, ptuple):
        widget = Qt.QComboBox()
        widget.setEditable(False)
        ppath = self.PROPERTY_ROOT + ptuple[0]
        widget.addItems(sorted(self.pattr(ptuple[2])))
        update = self.subscribe(ppath, callback=widget.setCurrentText)
        if update is None:
            raise TypeError('{} is not a writable property!'.format(ppath))
        def gui_changed(value):
            try:
                update(value)
            except rpc_client.RPCError as e:
                error = 'Could not set {} ({}).'.format(ppath, e.args[0])
                Qt.QMessageBox.warning(self, 'Invalid Value', error)
        widget.currentTextChanged.connect(gui_changed)
        return widget

    def make_objective_widget(self, ptuple):
        widget = Qt.QComboBox()
        widget.setEditable(False)
        ppath = self.PROPERTY_ROOT + ptuple[0]
        mags = self.pattr(ptuple[2])
        model = _ObjectivesModel(mags, widget.font(), self)
        widget.setModel(model)
        def prop_changed(value):
            widget.setCurrentIndex(value)
        update = self.subscribe(ppath, callback=prop_changed)
        if update is None:
            raise TypeError('{} is not a writable property!'.format(ppath))
        def gui_changed(value):
            try:
                update(value)
            except rpc_client.RPCError as e:
                error = 'Could not set {} ({}).'.format(ppath, e.args[0])
                Qt.QMessageBox.warning(self, 'Invalid Value', error)
        widget.currentIndexChanged[int].connect(gui_changed)
        return widget

class _ObjectivesModel(Qt.QAbstractListModel):
    def __init__(self, mags, font, parent=None):
        super().__init__(parent)
        self.mags = mags
        self.empty_pos_font = Qt.QFont(font)
        self.empty_pos_font.setItalic(True)

    def rowCount(self, _=None):
        return len(self.mags)

    def flags(self, midx):
        f = Qt.Qt.ItemNeverHasChildren
        if midx.isValid():
            row = midx.row()
            if row > 0:
                f |= Qt.Qt.ItemIsEnabled | Qt.Qt.ItemIsSelectable
        return f

    def data(self, midx, role=Qt.Qt.DisplayRole):
        if midx.isValid():
            row = midx.row()
            mag = self.mags[row]
            if role == Qt.Qt.DisplayRole:
                r = '{} : {}{}'.format(
                    row,
                    'BETWEEN POSITIONS' if row == 0 else mag,
                    '' if mag is None else 'x')
                return Qt.QVariant(r)
            if role == Qt.Qt.FontRole and mag is None:
                return Qt.QVariant(self.empty_pos_font)
        return Qt.QVariant()
