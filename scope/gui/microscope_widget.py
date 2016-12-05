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
# Authors: Zach Pincus <zpincus@wustl.edu> and Erik Hvatum <ice.rikh@gmail.com>

import enum
from pathlib import Path
from PyQt5 import Qt
from . import device_widget
from ..simple_rpc import rpc_client

class MicroscopeWidget(device_widget.DeviceWidget):
    PROPERTY_ROOT = 'scope.'
    PROPERTIES = [
        # tuple contains: property, type, and zero or more args that are passed to
        # the 'make_'+type+'widget() function.
#       ('stand.active_microscopy_method', 'enum', 'stand.available_microscopy_methods'),
        ('nosepiece.position', 'objective'),
#       ('nosepiece.safe_mode', 'bool'),
#       ('nosepiece.immersion_mode', 'bool'),
        ('il.shutter_open', 'bool'),
        ('tl.shutter_open', 'bool'),
        ('il.field_wheel', 'enum', 'il.field_wheel_positions'),
        ('il.filter_cube', 'enum', 'il.filter_cube_values'),
        # The final element of the 'tl.aperature_diaphragm' tuple, 'scope.nosepiece.position', indicates
        # that 'tl.aperture_diaphragm_range' may change with 'scope.nosepiece.position'.  So,
        # 'tl.aperture_diaphragm_range' should be refreshed upon 'scope.nosepiece.position' change.
        ('tl.aperture_diaphragm', 'int', 'tl.aperture_diaphragm_range', 'nosepiece.position'),
        ('tl.field_diaphragm', 'int', 'tl.field_diaphragm_range', 'nosepiece.position'),
        ('tl.condenser_retracted', 'bool'),
        ('stage.xy_fine_manual_control', 'bool'),
        ('stage.z_fine_manual_control', 'bool'),
        # TODO: use hard max values read from scope, if possible
        # TODO: If not possible, verify that hard max values are identical across all scopes
        # otherwise make this a config parameter.
        ('stage.x', 'stage_axis_pos', 225),
        ('stage.y', 'stage_axis_pos', 76),
        ('stage.z', 'stage_axis_pos', 26)
    ]

    @classmethod
    def can_run(cls, scope):
        # We're useful if at least one of our properties can be read.  Properties that can not be read
        # when the widget is created are not shown in the GUI.
        for property, *rest in cls.PROPERTIES:
            attr = scope
            try:
                for name in property.split('.'):
                    attr = getattr(attr, name)
            except:
                continue
            return True
        return False

    def __init__(self, host, scope, scope_properties, parent=None):
        super().__init__(host, scope, scope_properties, parent)
        self.limit_pixmaps_and_tooltips = LimitPixmapsAndToolTips()
        self.setWindowTitle('Microscope')
        self.setLayout(Qt.QGridLayout())
        self.scope = scope
        for property, widget_type, *widget_args in self.PROPERTIES:
            self.make_widgets_for_property(self.PROPERTY_ROOT + property, widget_type, widget_args)
        self.layout().addItem(Qt.QSpacerItem(
            0, 0, Qt.QSizePolicy.MinimumExpanding, Qt.QSizePolicy.MinimumExpanding), self.layout().rowCount(), 0,
            1,  # Spacer is just one logical row tall (that row stretches vertically to occupy all available space)...
            -1) # ... and, it spans all the columns in its row

    def get_scope_attr(self, property):
        """look up an attribute on the scope object by property name, which is
        expected to start with 'scope.' -- e.g. 'scope.stage.z_high_soft_limit'
        """
        attr = self.scope
        for name in property.split('.')[1:]:
            attr = getattr(attr, name)
        return attr

    def make_widgets_for_property(self, property, widget_type, widget_args):
        try:
            self.get_scope_attr(property)
        except AttributeError:
            # The property isn't available for this scope object, so don't
            # make a widget for it.
            # e = 'Failed to read value of "{}", so this property will not be presented in the GUI.'.format(property)
            # Qt.qDebug(e)
            return
        layout = self.layout()
        row = layout.rowCount()
        label = Qt.QLabel(property[len(self.PROPERTY_ROOT):] + ':') # strip the 'scope.' off
        layout.addWidget(label, row, 0)
        widget = getattr(self, 'make_{}_widget'.format(widget_type))(property, *widget_args)
        layout.addWidget(widget, row, 1)

    def make_bool_widget(self, property):
        widget = Qt.QCheckBox()
        update = self.subscribe(property, callback=widget.setChecked)
        if update is None:
            widget.setEnabled(False)
        else:
            def gui_changed(value):
                try:
                    update(value)
                except rpc_client.RPCError as e:
                    error = 'Could not set {} ({}).'.format(property, e.args[0])
                    Qt.QMessageBox.warning(self, 'Invalid Value', error)
            widget.toggled.connect(gui_changed)
        return widget

    def make_int_widget(self, property, range_property, range_depends_on_property):
        widget = Qt.QWidget()
        layout = Qt.QHBoxLayout()
        widget.setLayout(layout)
        slider = Qt.QSlider(Qt.Qt.Horizontal)
        slider.setTickInterval(1)
        layout.addWidget(slider)
        spinbox = Qt.QSpinBox()
        layout.addWidget(spinbox)
        handling_change = Condition() # acts as false, except when in a with-block, where it acts as true

        def range_changed(_):
            if handling_change:
                return
            with handling_change:
                range = self.get_scope_attr(self.PROPERTY_ROOT + range_property)
                slider.setRange(*range)
                spinbox.setRange(*range)
        self.subscribe(self.PROPERTY_ROOT + range_depends_on_property, callback=range_changed)

        def prop_changed(value):
            if handling_change:
                return
            with handling_change:
                slider.setValue(value)
                spinbox.setValue(value)
        update = self.subscribe(property, callback=prop_changed)

        if update is None:
            spinbox.setEnabled(False)
            slider.setEnabled(False)
        else:
            def gui_changed(value):
                if handling_change:
                    return
                with handling_change:
                    update(value)

            # TODO: verify the below doesn't blow up without indexing the
            # overloaded valueChanged signal as [int]
            slider.valueChanged.connect(gui_changed)
            spinbox.valueChanged.connect(gui_changed)
        return widget

    def make_enum_widget(self, property, choices_property):
        widget = Qt.QComboBox()
        widget.setEditable(False)
        widget.addItems(sorted(self.get_scope_attr(self.PROPERTY_ROOT + choices_property)))
        update = self.subscribe(property, callback=widget.setCurrentText)
        if update is None:
            widget.setEnabled(False)
        else:
            def gui_changed(value):
                try:
                    update(value)
                except rpc_client.RPCError as e:
                    error = 'Could not set {} ({}).'.format(property, e.args[0])
                    Qt.QMessageBox.warning(self, 'RPC Exception', error)
            widget.currentTextChanged.connect(gui_changed)
        return widget

    def make_objective_widget(self, property):
        widget = Qt.QComboBox()
        widget.setEditable(False)
        mags = self.get_scope_attr(self.PROPERTY_ROOT + 'nosepiece.all_objectives')
        model = _ObjectivesModel(mags, widget.font(), self)
        widget.setModel(model)
        def prop_changed(value):
            widget.setCurrentIndex(value)
        update = self.subscribe(property, callback=prop_changed)
        if update is None:
            widget.setEnabled(False)
        else:
            def gui_changed(value):
                try:
                    update(value)
                except rpc_client.RPCError as e:
                    error = 'Could not set {} ({}).'.format(property, e.args[0])
                    Qt.QMessageBox.warning(self, 'RPC Exception', error)
            # TODO: verify the below doesn't blow up without indexing the
            # overloaded currentIndexChanged signal as [int]
            widget.currentIndexChanged.connect(gui_changed)
        return widget

    def make_stage_axis_pos_widget(self, property, axis_max_val):
        widget = Qt.QWidget()
        vlayout = Qt.QVBoxLayout()
        widget.setLayout(vlayout)
        axis_name = property.split('.')[-1]
        props = self.scope_properties.properties # dict of tracked properties, updated by property client

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

        at_ls_property = self.PROPERTY_ROOT + 'stage.at_{}_low_soft_limit'.format(axis_name)
        at_lh_property = self.PROPERTY_ROOT + 'stage.at_{}_low_hard_limit'.format(axis_name)
        at_hs_property = self.PROPERTY_ROOT + 'stage.at_{}_high_soft_limit'.format(axis_name)
        at_hh_property = self.PROPERTY_ROOT + 'stage.at_{}_high_hard_limit'.format(axis_name)

        def at_low_limit_prop_changed(_):
            try:
                at_s = props[at_ls_property]
                at_h = props[at_lh_property]
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
        self.subscribe(at_ls_property, at_low_limit_prop_changed)
        self.subscribe(at_lh_property, at_low_limit_prop_changed)
        def at_high_limit_prop_changed(_):
            try:
                at_s = props[at_hs_property]
                at_h = props[at_hh_property]
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
        self.subscribe(at_hs_property, at_high_limit_prop_changed)
        self.subscribe(at_hh_property, at_high_limit_prop_changed)

        # [stop] [low soft limit text edit] [position text edit] [high soft limit text edit] [reset high soft limit button]
        hlayout = Qt.QHBoxLayout()
        stop_button = Qt.QPushButton(widget.style().standardIcon(Qt.QStyle.SP_BrowserStop), '')
        stop_button.setToolTip('Stop movement along {} axis.'.format(axis_name))
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
        self.subscribe('{}stage.moving_along_{}'.format(self.PROPERTY_ROOT, axis_name), moving_along_axis_changed)

        def stop_moving_along_axis():
            try:
                self.get_scope_attr(self.PROPERTY_ROOT+'stage.stop_{}'.format(axis_name))()
            except rpc_client.RPCError as e:
                error = 'Could not stop movement along {} axis ({}).'.format(axis_name, e.args[0])
                Qt.QMessageBox.warning(self, 'RPC Exception', error)
        # TODO: verify the below doesn't blow up without indexing the
        # overloaded clicked signal as [bool]
        stop_button.clicked.connect(stop_moving_along_axis)

        # low limit sub-widget
        low_limit_property = self.PROPERTY_ROOT + 'stage.{}_low_soft_limit'.format(axis_name)
        handling_low_soft_limit_change = Condition() # start out false, except when used as with-block context manager
        def low_limit_prop_changed(value):
            if handling_low_soft_limit_change:
                return
            with handling_low_soft_limit_change:
                low_limit_text_widget.setText(str(value))
                pos_text_validator.setBottom(value)
                high_limit_text_validator.setBottom(value)

        update_low_limit = self.subscribe(low_limit_property, low_limit_prop_changed)
        if update_low_limit is None:
            low_limit_text_widget.setEnabled(False)
        else:
            def submit_low_limit_text():
                if handling_low_soft_limit_change:
                    return
                with handling_low_soft_limit_change:
                    try:
                        new_low_limit = float(low_limit_text_widget.text())
                    except ValueError:
                        return
                    try:
                        update_low_limit(new_low_limit)
                    except rpc_client.RPCError as e:
                        error = 'Could not set {} axis to {} ({}).'format(axis_name, new_low_limit, e.args[0])
                        Qt.QMessageBox.warning(self, 'RPC Exception', error)
            low_limit_text_widget.returnPressed.connect(submit_low_limit_text)

            def low_limit_text_focus_lost():
                low_limit_text_widget.setText(str(props.get(low_limit_property, '')))

            low_limit_text_widget.focus_lost.connect(low_limit_text_focus_lost)

        # position sub-widget
        handling_pos_change = Condition()
        def position_changed(value):
            if handling_pos_change:
                return
            with handling_pos_change:
                pos_text_widget.setText(str(value))
                pos_slider.setValue(value * pos_slider_factor)

        self.subscribe(property, position_changed)
        get_pos = getattr(self.scope.stage, '_get_{}'.format(axis_name))
        set_pos = getattr(self.scope.stage, '_set_{}'.format(axis_name))

        def submit_pos_text():
            if handling_pos_change:
                return
            with handling_pos_change:
                try:
                    new_pos = float(pos_text_widget.text())
                except ValueError:
                    return
                if new_pos != get_pos():
                    try:
                        set_pos(new_pos, async='fire_and_forget')
                    except rpc_client.RPCError as e:
                        error = 'Could not set {} axis to {} ({}).'.format(axis_name, new_pos, e.args[0])
                        Qt.QMessageBox.warning(self, 'RPC Exception', error)
        pos_text_widget.returnPressed.connect(submit_pos_text)

        def pos_text_focus_lost():
            pos_text_widget.setText(str(props.get(property, '')))
        pos_text_widget.focus_lost.connect(pos_text_focus_lost)

        # high limit sub-widget
        high_limit_property = self.PROPERTY_ROOT + 'stage.{}_high_soft_limit'.format(axis_name)
        handling_high_soft_limit_change = Condition()
        def high_limit_prop_changed(value):
            if handling_high_soft_limit_change:
                return
            with handling_high_soft_limit_change:
                high_limit_text_widget.setText(str(value))
                pos_text_validator.setTop(value)
                low_limit_text_validator.setTop(value)
        update_high_limit = self.subscribe(high_limit_property, high_limit_prop_changed)
        if update_high_limit is None:
            high_limit_text_widget.setEnabled(False)
        else:
            def submit_high_limit_text():
                if handling_high_soft_limit_change:
                    return
                with handling_high_soft_limit_change:
                    try:
                        new_high_limit = float(high_limit_text_widget.text())
                    except ValueError:
                        return
                    try:
                        update_high_limit(new_high_limit)
                    except rpc_client.RPCError as e:
                        error = 'Could not set {} axis to {} ({}).'.format(name, new_high_limit, e.args[0])
                        Qt.QMessageBox.warning(self, 'RPC Exception', error)
            high_limit_text_widget.returnPressed.connect(submit_high_limit_text)

            def high_limit_text_focus_lost():
                high_limit_text_widget.setText(str(props.get(high_limit_property, '')))
            high_limit_text_widget.focus_lost.connect(high_limit_text_focus_lost)

        def reset_limits_button_clicked(_):
            update_low_limit(0.0)
            self.get_scope_attr(self.PROPERTY_ROOT + 'stage.reset_{}_high_soft_limit'.format(axis_name))()
        # TODO: verify the below doesn't blow up without indexing the
        # overloaded clicked signal as [bool]
        reset_limits_button.clicked.connect(reset_limits_button_clicked)

        # We do not receive events for z high soft limit changes initiated by means other than assigning
        # to scope.stage.z_high_soft_limit or calling scope.stage.reset_z_high_soft_limit().  However,
        # the scope's physical interface does not offer any way to modify z high soft limit, with one
        # possible exception: it would make sense for the limit to change with objective in order to prevent
        # head crashing.  In case that happens, we refresh z high soft limit upon objective change.
        # TODO: verify that this is never needed and get rid of it if so
        if axis_name is 'z':
            def objective_changed(_):
                if handling_high_soft_limit_change:
                    return
                with handling_high_soft_limit_change:
                    high_limit_text_widget.setText(str(self.get_scope_attr(self.PROPERTY_ROOT + 'stage.z_high_soft_limit')))
            self.subscribe(self.PROPERTY_ROOT + 'nosepiece.position', objective_changed)

        return widget

class Condition:
    def __init__(self):
        self.condition = False

    def __bool__(self):
        return self.condition

    def __enter__(self):
        self.condition = True

    def __exit__(self, *exc_info):
        self.condition = False

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
                r = '{}: {}{}'.format(
                    row,
                    'BETWEEN POSITIONS' if row == 0 else mag,
                    '' if mag is None else '×')
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

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setWidth(self.fontMetrics().width('44.57749') * 1.3)
        return hint