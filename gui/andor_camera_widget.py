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
# Authors: Erik Hvatum <ice.rikh@gmail.com>, Zach Pincus <zpincus@wustl.edu>
import math
from PyQt5 import Qt
from . import device_widget
from ..simple_rpc import rpc_client

INT_MIN, INT_MAX = 1, None
FLOAT_MIN, FLOAT_MAX, FLOAT_DECIMALS = 0, None, 3

class AndorCameraWidget(device_widget.DeviceWidget):
    PROPERTY_ROOT = 'scope.camera.'

    basic_properties = [ # list of properties to display, and logical range info if necessary
        'is_acquiring',
        'temperature_status',
        'sensor_temperature',
        'exposure_time',
        'binning',
        'aoi_left',
        'aoi_top',
        'aoi_width',
        'aoi_height',
        'sensor_gain',
        'pixel_readout_rate',
        'shutter_mode',
        'overlap_enabled',
        'cycle_mode',
        'frame_count',
        'frame_rate',
        'max_interface_fps',
        'readout_time',
        'trigger_mode'
    ]

    units = {
        'exposure_time': 'ms',
        'frame_rate': 'fps',
        'sensor_temperature': '°C',
        'readout_time': 'ms',
        'max_interface_fps': 'fps'
    }

    range_hints = {
        'exposure_time': (0.001, 30000, 3)
    }

    def __init__(self, scope, scope_properties, show_advanced=False, parent=None):
        super().__init__(scope, scope_properties, parent)
        self.setWindowTitle('Andor Camera ({})'.format(scope.camera.model_name))
        self.setLayout(Qt.QGridLayout())
        self.camera = scope.camera
        property_types = self.camera.andor_property_types
        advanced_properties = sorted(property_types.keys() - set(self.basic_properties))
        properties = [(property, False) for property in list(self.basic_properties)]
        properties+= [(advanced_property, True) for advanced_property in advanced_properties]
        self.advanced_widgets = [] # Widgets visible only when show all is enabled
        self._row = 0
        self.make_widgets_for_property('live_mode', 'Bool', readonly=False)
        for property in self.basic_properties:
            type, readonly = property_types[property]
            self.make_widgets_for_property(property, type, readonly)
        if advanced_properties:
            self.advanced_visibility_button = Qt.QPushButton()
            self.layout().addWidget(self.advanced_visibility_button, self._row, 0, 1, -1, Qt.Qt.AlignHCenter | Qt.Qt.AlignVCenter)
            self._row += 1
            for property in advanced_properties:
                type, readonly = property_types[property]
                self.advanced_widgets.extend(self.make_widgets_for_property(property, type, readonly))
            self._show_advanced = None
            self.show_advanced = show_advanced
            self.advanced_visibility_button.clicked.connect(self.show_advanced_clicked)
        self.layout().addItem(Qt.QSpacerItem(0, 0, Qt.QSizePolicy.MinimumExpanding, Qt.QSizePolicy.MinimumExpanding), self._row, 0,
                                             1,  # Spacer is just one logical row tall (that row stretches vertically to occupy all available space)...
                                             -1) # ... and, it spans all the columns in its row
        del self._row

    def make_widgets_for_property(self, property, type, readonly):
        label = Qt.QLabel(property + ':')
        self.layout().addWidget(label, self._row, 0)
        widget = self.make_widget(property, type, readonly)
        ret = [label, widget]
        self.layout().addWidget(widget, self._row, 1)
        if property in self.units:
            unit_label = Qt.QLabel(self.units[property])
            ret.append(unit_label)
            self.layout().addWidget(unit_label, self._row, 2)
        self._row += 1
        return ret

    def make_widget(self, property, type, readonly):
        if readonly:
            return self.make_readonly_widget(property)
        elif type in {'Int', 'Float'}:
            return self.make_numeric_widget(property, type)
        elif type == 'Enum':
            return self.make_enum_widget(property)
        elif type == 'Bool':
            return self.make_bool_widget(property)
        else: # we'll just treat it as readonly and show a string repr
            return self.make_readonly_widget(property)

    def make_readonly_widget(self, property):
        widget = Qt.QLabel()
        self.subscribe(self.PROPERTY_ROOT + property, callback=lambda value: widget.setText(str(value)))
        return widget

    def make_numeric_widget(self, property, type):
        widget = Qt.QLineEdit()
        widget.setValidator(self.get_numeric_validator(property, type))
        update = self.subscribe(self.PROPERTY_ROOT + property, callback=lambda value: widget.setText(str(value)))
        coerce_type = int if type == 'Int' else float
        def editing_finished():
            try:
                value = coerce_type(widget.text())
                update(value)
            except ValueError as e: # from the coercion
                Qt.QMessageBox.warning(self, 'Invalid Value', e.args[0])
            except rpc_client.RPCError as e: # from the update
                if e.args[0].find('OUTOFRANGE') != -1:
                    min, max = getattr(self.camera, property+'_range')
                    if min is None:
                        min = '?'
                    if max is None:
                        max = '?'
                    error = 'Given the camera state, {} must be in the range [{}, {}].'.format(property, min, max)
                elif e.args[0].find('NOTWRITABLE'):
                    error = 'Given the camera state, {} is not modifiable.'.format(property)
                else:
                    error = 'Could not set {} ({}).'.format(property, e.args[0])
                Qt.QMessageBox.warning(self, 'Invalid Value', error)
        widget.editingFinished.connect(editing_finished)
        return widget

    def get_numeric_validator(self, property, type):
        if type == 'Float':
            validator = Qt.QDoubleValidator()
            if property in self.range_hints:
                min, max, decimals = self.range_hints[property]
            else:
                min, max, decimals = FLOAT_MIN, FLOAT_MAX, FLOAT_DECIMALS
            if decimals is not None:
                validator.setDecimals(decimals)
        if type == 'Int':
            validator = Qt.QIntValidator()
            if property in self.range_hints:
                min, max = self.range_hints[property]
            else:
                min, max = INT_MIN, INT_MAX
        if min is not None:
            validator.setBottom(min)
        if max is not None:
            validator.setTop(max)
        return validator

    def make_enum_widget(self, property):
        widget = Qt.QComboBox()
        values = sorted(getattr(self.camera, property+'_values').keys())
        indices = {v:i for i, v in enumerate(values)}
        widget.addItems(values)
        update = self.subscribe(self.PROPERTY_ROOT + property, callback=lambda value: widget.setCurrentIndex(indices[value]))
        def changed(value):
            try:
                update(value)
            except rpc_client.RPCError as e:
                if e.args[0].find('NOTAVAILABLE'):
                    accepted_values = sorted(k for k, v in getattr(self.camera, property+'_values').items() if v)
                    error = 'Given the camera state, {} can only be one of [{}].'.format(property, ', '.join(accepted_values))
                else:
                    error = 'Could not set {} ({}).'.format(property, e.args[0])
                Qt.QMessageBox.warning(self, 'Invalid Value', error)
        widget.currentIndexChanged[str].connect(changed)
        return widget

    def make_bool_widget(self, property):
        widget = Qt.QCheckBox()
        update = self.subscribe(self.PROPERTY_ROOT + property, callback=widget.setChecked)
        def changed(value):
            try:
                update(value)
            except rpc_client.RPCError as e:
                if e.args[0].find('NOTWRITABLE'):
                    error = "Given the camera state, {} can't be changed.".format(property)
                else:
                    error = 'Could not set {} ({}).'.format(property, e.args[0])
                Qt.QMessageBox.warning(self, 'Invalid Value', error)
        widget.toggled.connect(changed)
        return widget

    @property
    def show_advanced(self):
        if self.advanced_widgets:
            return self._show_advanced

    @show_advanced.setter
    def show_advanced(self, show_advanced):
        if self.advanced_widgets:
            if show_advanced != self._show_advanced:
                self.advanced_visibility_button.setText('Hide Advanced ▼' if show_advanced else 'Show Advanced ▷')
                for widget in self.advanced_widgets:
                    widget.setVisible(show_advanced)
                self._show_advanced = show_advanced

    def show_advanced_clicked(self):
        self.show_advanced = not self.show_advanced
