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
        # TODO: use hard max values read from scope, if possible
        ('stage.x', PT.StageAxisPos, 'stage', 'x', 225),
        ('stage.y', PT.StageAxisPos, 'stage', 'y', 76),
        ('stage.z', PT.StageAxisPos, 'stage', 'z', 26, 'nosepiece.position')
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
        self.limit_pixmaps_and_tooltips = LimitPixmapsAndToolTips()
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
        self.layout().addItem(Qt.QSpacerItem(
            0, 0, Qt.QSizePolicy.MinimumExpanding, Qt.QSizePolicy.MinimumExpanding), self.layout().rowCount(), 0,
            1,  # Spacer is just one logical row tall (that row stretches vertically to occupy all available space)...
            -1) # ... and, it spans all the columns in its row

    def pattr(self, ppath):
        attr = self.scope
        for attr_name in ppath.split('.'):
            attr = getattr(attr, attr_name)
        return attr

    def make_widgets_for_property(self, ptuple):
        try:
            self.pattr(ptuple[0])
        except:
            e = 'Failed to read value of "{}{}", so this property will not be presented in the GUI.'
            Qt.qDebug(e.format(self.PROPERTY_ROOT, ptuple[0]))
            return
        layout = self.layout()
        row = layout.rowCount()
        label = Qt.QLabel(ptuple[0] + ':')
        layout.addWidget(label, row, 0)
        widget = self.widget_makers[ptuple[1]](*ptuple)
        layout.addWidget(widget, row, 1)
        return label, widget

    def make_bool_widget(self, rppath, pt):
        widget = Qt.QCheckBox()
        ppath = self.PROPERTY_ROOT + rppath
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

    def make_int_widget(self, rppath, pt, range_rppath, provoke_update_rppath):
        widget = Qt.QWidget()
        ppath = self.PROPERTY_ROOT + rppath
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
                range_ = self.pattr(range_rppath)
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
        self.subscribe(self.PROPERTY_ROOT + provoke_update_rppath, callback=range_changed)
        slider.valueChanged[int].connect(gui_changed)
        spinbox.valueChanged[int].connect(gui_changed)
        return widget

    def make_enum_widget(self, rppath, pt, choices_rppath):
        widget = Qt.QComboBox()
        widget.setEditable(False)
        ppath = self.PROPERTY_ROOT + rppath
        widget.addItems(sorted(self.pattr(choices_rppath)))
        update = self.subscribe(ppath, callback=widget.setCurrentText)
        if update is None:
            raise TypeError('{} is not a writable property!'.format(ppath))
        def gui_changed(value):
            try:
                update(value)
            except rpc_client.RPCError as e:
                error = 'Could not set {} ({}).'.format(ppath, e.args[0])
                Qt.QMessageBox.warning(self, 'RPC Exception', error)
        widget.currentTextChanged.connect(gui_changed)
        return widget

    def make_objective_widget(self, rppath, pt, objectives_rppath):
        widget = Qt.QComboBox()
        widget.setEditable(False)
        ppath = self.PROPERTY_ROOT + rppath
        mags = self.pattr(objectives_rppath)
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
                Qt.QMessageBox.warning(self, 'RPC Exception', error)
        widget.currentIndexChanged[int].connect(gui_changed)
        return widget

    def make_stage_axis_pos_widget(self, rppath, pt, stage_rppath, axis_name, axis_max_val, provoke_update_rppath=None):
        device = self.pattr(stage_rppath)
        widget = Qt.QWidget()
        vlayout = Qt.QVBoxLayout()
        widget.setLayout(vlayout)
        handling_low_soft_limit_change = False
        handling_high_soft_limit_change = False
        handling_pos_change = False
        props = self.scope_properties.properties
        low_limit_rppath = '{}.{}_low_soft_limit'.format(stage_rppath, axis_name)
        low_limit_ppath = self.PROPERTY_ROOT + low_limit_rppath
        pos_ppath = self.PROPERTY_ROOT + rppath
        high_limit_rppath = '{}.{}_high_soft_limit'.format(stage_rppath, axis_name)
        high_limit_ppath = self.PROPERTY_ROOT + high_limit_rppath

        # [low limits status indicator] [-------<slider>-------] [high limits status indicator]
        hlayout = Qt.QHBoxLayout()
        low_limit_status_label = Qt.QLabel()
        # NB: *_limit_status_label pixmaps are set here so that layout does not jump when limit status RPC property updates
        # are first received
        low_limit_status_label.setPixmap(self.limit_pixmaps_and_tooltips.low_no_limit_pm)
        hlayout.addWidget(low_limit_status_label)
        pos_slider_factor = 1e5
        pos_slider = Qt.QSlider(Qt.Qt.Horizontal)
        pos_slider.setEnabled(False)
        pos_slider.setRange(0, pos_slider_factor * axis_max_val)
        hlayout.addWidget(pos_slider)
        high_limit_status_label = Qt.QLabel()
        high_limit_status_label.setPixmap(self.limit_pixmaps_and_tooltips.high_no_limit_pm)
        hlayout.addWidget(high_limit_status_label)
        vlayout.addLayout(hlayout)
        at_ls_pname = '{}{}.at_{}_low_soft_limit'.format(self.PROPERTY_ROOT, stage_rppath, axis_name)
        at_lh_pname = '{}{}.at_{}_low_hard_limit'.format(self.PROPERTY_ROOT, stage_rppath, axis_name)
        def at_low_limit_prop_changed(_):
            try:
                at_s = props[at_ls_pname]
                at_h = props[at_lh_pname]
            except KeyError:
                return
            if at_s and at_h:
                pm = self.limit_pixmaps_and_tooltips.low_hard_and_soft_limits_pm
                tt = self.limit_pixmaps_and_tooltips.low_hard_and_soft_limits_tt
            elif at_s:
                pm = self.limit_pixmaps_and_tooltips.low_soft_limit_pm
                tt = self.limit_pixmaps_and_tooltips.low_soft_limit_tt
            elif at_h:
                pm = self.limit_pixmaps_and_tooltips.low_hard_limit_pm
                tt = self.limit_pixmaps_and_tooltips.low_hard_limit_tt
            else:
                pm = self.limit_pixmaps_and_tooltips.low_no_limit_pm
                tt = self.limit_pixmaps_and_tooltips.low_no_limit_tt
            low_limit_status_label.setPixmap(pm)
            low_limit_status_label.setToolTip(tt)
        self.subscribe(at_ls_pname, at_low_limit_prop_changed)
        self.subscribe(at_lh_pname, at_low_limit_prop_changed)
        at_hs_pname = '{}{}.at_{}_high_soft_limit'.format(self.PROPERTY_ROOT, stage_rppath, axis_name)
        at_hh_pname = '{}{}.at_{}_high_hard_limit'.format(self.PROPERTY_ROOT, stage_rppath, axis_name)
        def at_high_limit_prop_changed(_):
            try:
                at_s = props[at_hs_pname]
                at_h = props[at_hh_pname]
            except KeyError:
                return
            if at_s and at_h:
                pm = self.limit_pixmaps_and_tooltips.high_hard_and_soft_limits_pm
                tt = self.limit_pixmaps_and_tooltips.high_hard_and_soft_limits_tt
            elif at_s:
                pm = self.limit_pixmaps_and_tooltips.high_soft_limit_pm
                tt = self.limit_pixmaps_and_tooltips.high_soft_limit_tt
            elif at_h:
                pm = self.limit_pixmaps_and_tooltips.high_hard_limit_pm
                tt = self.limit_pixmaps_and_tooltips.high_hard_limit_tt
            else:
                pm = self.limit_pixmaps_and_tooltips.high_no_limit_pm
                tt = self.limit_pixmaps_and_tooltips.high_no_limit_tt
            high_limit_status_label.setPixmap(pm)
            high_limit_status_label.setToolTip(tt)
        self.subscribe(at_hs_pname, at_high_limit_prop_changed)
        self.subscribe(at_hh_pname, at_high_limit_prop_changed)

        # [stop] [low soft limit text edit] [position text edit] [high soft limit text edit] [reset high soft limit button]
        hlayout = Qt.QHBoxLayout()
        stop_button = Qt.QPushButton(widget.style().standardIcon(Qt.QStyle.SP_BrowserStop), '')
        stop_button.setToolTip('Stop movement along {}.'.format(rppath))
        stop_button.setEnabled(False)
        hlayout.addWidget(stop_button)
        low_limit_text_widget = FocusLossSignalingLineEdit()
        low_limit_text_widget.setMaxLength(8)
        low_limit_text_validator = Qt.QDoubleValidator()
        low_limit_text_validator.setBottom(0)
        low_limit_text_widget.setValidator(low_limit_text_validator)
        hlayout.addWidget(low_limit_text_widget)
        pos_text_widget = FocusLossSignalingLineEdit()
        pos_text_widget.setMaxLength(8)
        pos_text_validator = Qt.QDoubleValidator()
        pos_text_widget.setValidator(pos_text_validator)
        hlayout.addWidget(pos_text_widget)
        high_limit_text_widget = FocusLossSignalingLineEdit()
        high_limit_text_widget.setMaxLength(8)
        high_limit_text_validator = Qt.QDoubleValidator()
        high_limit_text_validator.setTop(axis_max_val)
        high_limit_text_widget.setValidator(high_limit_text_validator)
        hlayout.addWidget(high_limit_text_widget)
        reset_limits_button = Qt.QPushButton('Reset limits')
        reset_limits_button.setToolTip(
            'Reset {} soft min and max to the smallest \n and largest acceptable values, respectively.'.format(axis_name)
        )
        hlayout.addWidget(reset_limits_button)
        vlayout.addLayout(hlayout)
        def moving_along_axis_changed(value):
            stop_button.setEnabled(value)
        def stop_moving_along_axis():
            try:
                self.pattr('{}.stop_{}'.format(stage_rppath, axis_name))()
            except rpc_client.RPCError as e:
                error = 'Could not stop movement along {} ({}).'.format(rppath, e.args[0])
                Qt.QMessageBox.warning(self, 'RPC Exception', error)
        def low_limit_prop_changed(value):
            nonlocal handling_low_soft_limit_change
            if handling_low_soft_limit_change:
                return
            handling_low_soft_limit_change = True
            try:
                low_limit_text_widget.setText(str(value))
                pos_text_validator.setBottom(value)
                high_limit_text_validator.setBottom(value)
            finally:
                handling_low_soft_limit_change = False
        def submit_low_limit_text():
            nonlocal handling_low_soft_limit_change
            if handling_low_soft_limit_change:
                return
            handling_low_soft_limit_change = True
            try:
                new_low_limit = float(low_limit_text_widget.text())
                try:
                    update_low_limit(new_low_limit)
                except rpc_client.RPCError as e:
                    error = 'Could not set {}.{} to {} ({}).'
                    error = error.format(stage_rppath, axis_name, new_low_limit, e.args[0])
                    Qt.QMessageBox.warning(self, 'RPC Exception', error)
            except ValueError:
                pass
            finally:
                handling_low_soft_limit_change = False
        def low_limit_text_focus_lost():
            low_limit_text_widget.setText(str(props.get(low_limit_ppath, '')))
        def pos_prop_changed(value):
            nonlocal handling_pos_change
            if handling_pos_change:
                return
            handling_pos_change = True
            try:
                pos_text_widget.setText(str(value))
                pos_slider.setValue(value * pos_slider_factor)
            finally:
                handling_pos_change = False
        def submit_pos_text():
            nonlocal handling_pos_change
            if handling_pos_change:
                return
            handling_pos_change = True
            try:
                new_pos = float(pos_text_widget.text())
                if new_pos != get_pos():
                    try:
                        set_pos(new_pos, async='fire_and_forget')
                    except rpc_client.RPCError as e:
                        error = 'Could not set {} to {} ({}).'.format(rppath, new_pos, e.args[0])
                        Qt.QMessageBox.warning(self, 'RPC Exception', error)
            except ValueError:
                pass
            finally:
                handling_pos_change = False
        def pos_text_focus_lost():
            pos_text_widget.setText(str(props.get(pos_ppath, '')))
        def high_limit_prop_changed(value):
            nonlocal handling_high_soft_limit_change
            if handling_high_soft_limit_change:
                return
            handling_high_soft_limit_change = True
            try:
                high_limit_text_widget.setText(str(value))
                pos_text_validator.setTop(value)
                low_limit_text_validator.setTop(value)
            finally:
                handling_high_soft_limit_change = False
        def submit_high_limit_text():
            nonlocal handling_high_soft_limit_change
            if handling_high_soft_limit_change:
                return
            handling_high_soft_limit_change = True
            try:
                new_high_limit = float(high_limit_text_widget.text())
                try:
                    update_high_limit(new_high_limit)
                except rpc_client.RPCError as e:
                    error = 'Could not set {}.{} to {} ({}).'
                    error = error.format(stage_rppath, axis_name, new_high_limit, e.args[0])
                    Qt.QMessageBox.warning(self, 'RPC Exception', error)
            except ValueError:
                pass
            finally:
                handling_high_soft_limit_change = False
        def high_limit_text_focus_lost():
            high_limit_text_widget.setText(str(props.get(high_limit_ppath, '')))
        def reset_limits_button_clicked(_):
            update_low_limit(0.0)
            self.pattr('{}.reset_{}_high_soft_limit'.format(stage_rppath, axis_name))()
            
        stop_button.clicked[bool].connect(stop_moving_along_axis)
        self.subscribe('{}{}.moving_along_{}'.format(self.PROPERTY_ROOT, stage_rppath, axis_name), moving_along_axis_changed)
        update_low_limit = self.subscribe(low_limit_ppath, low_limit_prop_changed)
        if update_low_limit is None:
            raise TypeError('{} is not a writable property!'.format(low_limit_ppath))
        low_limit_text_widget.returnPressed.connect(submit_low_limit_text)
        low_limit_text_widget.focus_lost.connect(low_limit_text_focus_lost)
        self.subscribe(pos_ppath, pos_prop_changed)
        get_pos = getattr(device, '_get_{}'.format(axis_name))
        set_pos = getattr(device, '_set_{}'.format(axis_name))
        pos_text_widget.returnPressed.connect(submit_pos_text)
        pos_text_widget.focus_lost.connect(pos_text_focus_lost)
        update_high_limit = self.subscribe(high_limit_ppath, high_limit_prop_changed)
        if update_high_limit is None:
            raise TypeError('{} is not a writable property!'.format(high_limit_ppath))
        high_limit_text_widget.returnPressed.connect(submit_high_limit_text)
        high_limit_text_widget.focus_lost.connect(high_limit_text_focus_lost)
        reset_limits_button.clicked[bool].connect(reset_limits_button_clicked)

        # We do not receive events for z high soft limit changes initiated by means other than assigning
        # to scope.stage.z_high_soft_limit or calling scope.stage.reset_z_high_soft_limit().  However,
        # the scope's physical interface does not offer any way to modify z high soft limit, with one
        # possible exception: it would make sense for the limit to change with objective in order to prevent
        # head crashing.  In case that happens, we refresh z high soft limit upon objective change.
        # TODO: verify that this is never needed and get rid of it if so
        if provoke_update_rppath is not None:
            def objective_changed(_):
                nonlocal handling_high_soft_limit_change
                if handling_high_soft_limit_change:
                    return
                handling_high_soft_limit_change = True
                try:
                    high_limit_text_widget.setText(str(self.pattr('{}.{}_high_soft_limit'.format(stage_rppath, axis_name))))
                finally:
                    handling_high_soft_limit_change = False
            self.subscribe(self.PROPERTY_ROOT + provoke_update_rppath, objective_changed)

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

class LimitPixmapsAndToolTips:
    def __init__(self, height=25):
        def load(fpath):
            im = Qt.QImage(str(fpath)).scaledToHeight(height)
            setattr(self, 'low_'+fpath.stem+'_pm', Qt.QPixmap.fromImage(im))
            setattr(self, 'high_'+fpath.stem+'_pm', Qt.QPixmap.fromImage(im.transformed(flip)))
            setattr(self, 'low_'+fpath.stem+'_tt', fpath.stem[0].capitalize() + fpath.stem[1:].replace('_', ' ') + ' reached.')
            setattr(self, 'high_'+fpath.stem+'_tt', fpath.stem[0].capitalize() + fpath.stem[1:].replace('_', ' ') + ' reached.')
        dpath = Path(__file__).parent / 'limit_icons'
        flip = Qt.QTransform()
        flip.rotate(180)
        for fname in ('no_limit.svg', 'soft_limit.svg', 'hard_limit.svg', 'hard_and_soft_limits.svg'):
            load(dpath / fname)

class FocusLossSignalingLineEdit(Qt.QLineEdit):
    focus_lost = Qt.pyqtSignal()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.focus_lost.emit()
