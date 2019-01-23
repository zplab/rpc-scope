# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt
from . import device_widget
from ..simple_rpc import rpc_client

DEFAULT_PROP = dict(andor_type='String', read_only=True, units=None)

class AndorCameraWidget(device_widget.DeviceWidget):
    PROPERTY_ROOT = 'scope.camera.'

    def __init__(self, scope, parent=None):
        super().__init__(scope, parent)
        self.camera_properties = dict(self.scope.camera.camera_properties)
        self.build_gui()

    def build_gui(self):
        self.setWindowTitle('Camera')
        self.add_property_rows(self.scope.camera.basic_properties)

    def add_property_rows(self, properties):
        form = Qt.QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setVerticalSpacing(5)
        form.setLabelAlignment(Qt.Qt.AlignRight)
        form.setFieldGrowthPolicy(Qt.QFormLayout.ExpandingFieldsGrow)
        self.setLayout(form)
        for row, prop in enumerate(properties):
            self.make_widgets_for_property(row, prop)

    def make_widgets_for_property(self, row, prop):
        prop_data = self.camera_properties.get(prop, DEFAULT_PROP)
        # prop_data is a dict with keys 'andor_type', 'read_only', and 'units'
        # DEFAULT_PROP is just to assume a readonly string property if we don't have more information.
        widget = self.make_widget(prop, prop_data)
        units = prop_data['units']
        if units is not None:
            layout = Qt.QHBoxLayout()
            layout.addWidget(widget)
            layout.addWidget( Qt.QLabel(units))
            layout.setSpacing(4)
            widget = layout
        self.layout().addRow(prop + ':', widget)

    def make_widget(self, prop, prop_data):
        if prop_data['read_only']:
            return self.make_readonly_widget(prop)

        andor_type = prop_data['andor_type']
        if andor_type in {'Int', 'Float'}:
            return self.make_numeric_widget(prop, prop_data)
        elif andor_type == 'Enum':
            return self.make_enum_widget(prop)
        elif andor_type == 'Bool':
            return self.make_bool_widget(prop)
        else: # we'll just treat it as readonly and show a string repr
            return self.make_readonly_widget(prop)

    def make_readonly_widget(self, prop):
        widget = Qt.QLabel()
        if prop.endswith('_range'):
            def receive_update(value):
                mx, mn = value
                widget.setText(f'{mn:.3g}\N{THIN SPACE}\N{EN DASH}\N{THIN SPACE}{mx:.3g}')
        else:
            def receive_update(value):
                if isinstance(value, float):
                    text = f'{value:.3g}'
                else:
                    text = str(value)
                widget.setText(text)

        self.subscribe(self.PROPERTY_ROOT + prop, callback=receive_update, readonly=True)
        return widget

    def make_numeric_widget(self, prop, prop_data):
        andor_type = prop_data['andor_type']
        if andor_type == 'Float':
            validator = Qt.QDoubleValidator()
            coerce_type = float
        else: # andor_type == 'Int'
            validator = Qt.QIntValidator()
            coerce_type = int
        widget = Qt.QLineEdit()
        widget.setValidator(validator)
        def receive_update(value):
            widget.setText(f'{value:.3g}')

        update = self.subscribe(self.PROPERTY_ROOT + prop, callback=receive_update)
        if update is None:
            raise TypeError('{} is not a writable property!'.format(prop))

        def editing_finished():
            try:
                value = coerce_type(widget.text())
                update(value)
            except ValueError as e: # from the coercion
                Qt.QMessageBox.warning(self, 'Invalid Value', e.args[0])
            except rpc_client.RPCError as e: # from the update
                if e.args[0].find('OUTOFRANGE') != -1:
                    valid_min, valid_max = getattr(self.scope.camera, prop+'_range')
                    if value < valid_min:
                        update(valid_min)
                    elif value > valid_max:
                        update(valid_max)
                elif e.args[0].find('NOTWRITABLE') != -1:
                    error = 'Given the camera state, {} is not modifiable.'.format(prop)
                else:
                    error = 'Could not set {} ({}).'.format(prop, e.args[0])
                Qt.QMessageBox.warning(self, 'Invalid Value', error)

        widget.editingFinished.connect(editing_finished)
        return widget

    def make_enum_widget(self, prop):
        widget = Qt.QComboBox()
        values = sorted(getattr(self.scope.camera, prop+'_values').keys())
        indices = {v: i for i, v in enumerate(values)}
        widget.addItems(values)
        def receive_update(value):
            widget.setCurrentIndex(indices[value])

        update = self.subscribe(self.PROPERTY_ROOT + prop, callback=receive_update)
        if update is None:
            raise TypeError('{} is not a writable property!'.format(prop))

        def changed(value):
            try:
                update(value)
            except rpc_client.RPCError as e:
                if e.args[0].find('NOTWRITABLE') != -1:
                    error = "Given the camera state, {} can't be changed.".format(prop)
                elif e.args[0].find('NOTAVAILABLE') != -1:
                    accepted_values = sorted(k for k, v in getattr(self.scope.camera, prop+'_values').items() if v)
                    error = 'Given the camera state, {} can only be one of [{}].'.format(prop, ', '.join(accepted_values))
                else:
                    error = 'Could not set {} ({}).'.format(prop, e.args[0])
                Qt.QMessageBox.warning(self, 'Invalid Value', error)
        widget.currentIndexChanged[str].connect(changed)
        return widget

    def make_bool_widget(self, prop):
        widget = Qt.QCheckBox()
        update = self.subscribe(self.PROPERTY_ROOT + prop, callback=widget.setChecked)
        if update is None:
            raise TypeError('{} is not a writable property!'.format(prop))
        def changed(value):
            try:
                update(value)
            except rpc_client.RPCError as e:
                if e.args[0].find('NOTWRITABLE') != -1:
                    error = "Given the camera state, {} can't be changed.".format(prop)
                else:
                    error = 'Could not set {} ({}).'.format(prop, e.args[0])
                Qt.QMessageBox.warning(self, 'Invalid Value', error)
        widget.toggled.connect(changed)
        return widget


class AndorAdvancedCameraWidget(AndorCameraWidget):
    def build_gui(self):
        self.setWindowTitle('Adv. Camera')
        advanced_properties = sorted(self.camera_properties.keys() - set(self.scope.camera.basic_properties))
        self.add_property_rows(advanced_properties)
