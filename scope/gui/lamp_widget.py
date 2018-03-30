# This code is licensed under the MIT License (see LICENSE file for details)

from . import device_widget
from PyQt5 import Qt

class LampWidget(device_widget.DeviceWidget):
    @staticmethod
    def can_run(scope):
        return device_widget.has_component(scope, 'scope.tl.lamp') or device_widget.has_component(scope, 'scope.il.spectra')

    def __init__(self, scope, scope_properties, parent=None):
        super().__init__(scope, scope_properties, parent)
        self.setWindowTitle('Lamps')
        container_layout = Qt.QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        self.setLayout(container_layout)

        grid_layout = Qt.QGridLayout()
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(4)
        container_layout.addLayout(grid_layout)

        self.lamp_controllers = []
        if device_widget.has_component(scope, 'scope.tl.lamp'):
            self.lamp_controllers.append(LampController(self, 'scope.tl.lamp', grid_layout))

        if device_widget.has_component(scope, 'scope.il.spectra'):
            lamp_specs = scope.il.spectra.lamp_specs
            # sort lamp names by the values of the lamp_specs dict; to wit, the center wavelengths
            lamps = sorted(lamp_specs.keys(), key=lamp_specs.get)
            self.lamp_controllers += [LampController(self, 'scope.il.spectra.'+lamp, grid_layout) for lamp in lamps]

class LampController:
    def __init__(self, widget, name, layout):
        display_name = name.split('.', 1)[1] # strip off leading 'scope.'
        toggle = Qt.QCheckBox(display_name)
        row = layout.rowCount()
        layout.addWidget(toggle, row, 0)
        toggle_update = widget.subscribe(name + '.enabled', callback=toggle.setChecked)
        toggle.toggled.connect(toggle_update)
        self.toggle = toggle

        slider = Qt.QSlider(Qt.Qt.Horizontal)
        layout.addWidget(slider, row, 1)
        slider.setRange(0, 255)
        slider.setSingleStep(1)
        slider.setPageStep(5)
        slider.setValue(0)
        slider.setMinimumWidth(255)
        slider.setMaximumWidth(255)

        spinbox = Qt.QSpinBox()
        layout.addWidget(spinbox, row, 2)
        spinbox.setRange(0, 255)
        spinbox.setSingleStep(1)
        spinbox.setValue(0)
        spinbox.setSizePolicy(Qt.QSizePolicy.Fixed, Qt.QSizePolicy.Fixed)
        self.spinbox = spinbox

        self.update_spx = widget.subscribe(name + '.intensity', callback=slider.setValue)
        # note that giving slider.setValue as the callback will work fine. That will cause a slider.valueChanged
        # signal, which due to the slider_changed() function will cause the spinbox to be updated too.
        # It also calls update_spx(), which seems like an odd thing to fire off in response to getting
        # an update *from* the spectra x. But update_spx is smart enough to not actually do anything in
        # response to trying to update a value to the value it already is...
        slider.valueChanged.connect(self.slider_changed)
        spinbox.valueChanged.connect(slider.setValue)

    def slider_changed(self, value):
        self.spinbox.setValue(value)
        self.update_spx(value)
