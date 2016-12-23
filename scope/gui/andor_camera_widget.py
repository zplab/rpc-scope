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
from . import device_widget
from ..simple_rpc import rpc_client

INT_MIN, INT_MAX = 1, None
FLOAT_MIN, FLOAT_MAX, FLOAT_DECIMALS = 0, None, 3

# TODO: make advanced properties a separate widget.

class AndorCameraWidget(device_widget.DeviceWidget):
    PROPERTY_ROOT = 'scope.camera.'

    PROPERTIES = [ # list of properties to display, and logical range info if necessary
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
        'readout_rate',
        'shutter_mode',
        'overlap_enabled',
        'cycle_mode',
        'frame_count',
        'frame_rate',
        'frame_rate_range',
        'max_interface_fps',
        'readout_time',
        'trigger_mode'
    ]

    UNITS = {
        'exposure_time': 'ms',
        'frame_rate': 'fps',
        'sensor_temperature': '°C',
        'readout_time': 'ms',
        'max_interface_fps': 'fps'
    }

    RANGE_HINTS = {
        'exposure_time': (0.001, 30000, 3)
    }

    def __init__(self, host, scope, scope_properties, parent=None):
        super().__init__(host, scope, scope_properties, parent)
        self.camera = scope.camera
        self.build_gui()

    def build_gui(self):
        self.setWindowTitle('Andor Camera ({})'.format(self.camera.model_name))
        properties = ['live_mode'] + self.PROPERTIES
        property_types = dict(self.camera.andor_property_types)
        property_types['live_mode'] = ('Bool', False)
        self.add_property_rows(properties, property_types)

    def add_property_rows(self, properties, property_types):
        self.setLayout(Qt.QGridLayout())
        for row, property in enumerate(properties):
            type, readonly = property_types.get(property, ('String', True)) # if the property type isn't in the dict, assume its a readonly string
            self.make_widgets_for_property(property, type, readonly)
        self.layout().addItem(Qt.QSpacerItem(0, 0, Qt.QSizePolicy.MinimumExpanding, Qt.QSizePolicy.MinimumExpanding), row+1, 0,
                                             1,  # Spacer is just one logical row tall (that row stretches vertically to occupy all available space)...
                                             -1) # ... and, it spans all the columns in its row

    def make_widgets_for_property(self, row, property, type, readonly):
        label = Qt.QLabel(property + ':')
        self.layout().addWidget(label, row, 0)
        widget = self.make_widget(property, type, readonly)
        ret = [label, widget]
        self.layout().addWidget(widget, row, 1)
        if property in self.UNITS:
            unit_label = Qt.QLabel(self.UNITS[property])
            ret.append(unit_label)
            self.layout().addWidget(unit_label, row, 2)
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
        if update is None:
            raise TypeError('{} is not a writable property!'.format(property))
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
                elif e.args[0].find('NOTWRITABLE') != -1:
                    error = 'Given the camera state, {} is not modifiable.'.format(property)
                else:
                    error = 'Could not set {} ({}).'.format(property, e.args[0])
                Qt.QMessageBox.warning(self, 'Invalid Value', error)
        widget.editingFinished.connect(editing_finished)
        return widget

    def get_numeric_validator(self, property, type):
        if type == 'Float':
            validator = Qt.QDoubleValidator()
            if property in self.RANGE_HINTS:
                min, max, decimals = self.RANGE_HINTS[property]
            else:
                min, max, decimals = FLOAT_MIN, FLOAT_MAX, FLOAT_DECIMALS
            if decimals is not None:
                validator.setDecimals(decimals)
        if type == 'Int':
            validator = Qt.QIntValidator()
            if property in self.RANGE_HINTS:
                min, max = self.RANGE_HINTS[property]
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
        if update is None:
            raise TypeError('{} is not a writable property!'.format(property))
        def changed(value):
            try:
                update(value)
            except rpc_client.RPCError as e:
                if e.args[0].find('NOTWRITABLE') != -1:
                    error = "Given the camera state, {} can't be changed.".format(property)
                elif e.args[0].find('NOTAVAILABLE') != -1:
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
        if update is None:
            raise TypeError('{} is not a writable property!'.format(property))
        def changed(value):
            try:
                update(value)
            except rpc_client.RPCError as e:
                if e.args[0].find('NOTWRITABLE') != -1:
                    error = "Given the camera state, {} can't be changed.".format(property)
                else:
                    error = 'Could not set {} ({}).'.format(property, e.args[0])
                Qt.QMessageBox.warning(self, 'Invalid Value', error)
        widget.toggled.connect(changed)
        return widget


class AndorAdvancedCameraWidget(AndorCameraWidget):
    def build_gui(self):
        self.setWindowTitle('Advanced Camera Settings')
        property_types = dict(self.camera.andor_property_types)
        advanced_properties = sorted(property_types.keys() - set(self.PROPERTIES))
        self.add_property_rows(advanced_properties, property_types)