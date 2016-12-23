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

from . import device_widget
from PyQt5 import Qt

class SpectraXWidget(device_widget.DeviceWidget):
    PROPERTY_ROOT = 'scope.il.spectra.'

    def __init__(self, host, scope, scope_properties, parent=None):
        super().__init__(host, scope, scope_properties, parent)
        self.setWindowTitle('Spectra X')
        container_layout = Qt.QVBoxLayout()
        self.setLayout(container_layout)
        
        grid_layout = Qt.QGridLayout()
        container_layout.addLayout(grid_layout)

        lamp_specs = scope.il.spectra.lamp_specs
        # sort lamp names by the values of the lamp_specs dict; to wit, the center wavelengths
        lamps = sorted(lamp_specs.keys(), key=lamp_specs.get)
        self.lamp_controllers = [LampController(self, self.PROPERTY_ROOT+lamp, grid_layout, i) for i, lamp in enumerate(lamps)]

        bottom_layout = Qt.QHBoxLayout()
        container_layout.addLayout(bottom_layout)
        disable_all_button = Qt.QPushButton('Disable All')
        bottom_layout.addWidget(disable_all_button)
        disable_all_button.clicked.connect(self.disable_all)
        temperature_label = Qt.QLabel('Temperature: -')
        bottom_layout.addWidget(temperature_label)
        self.subscribe(self.PROPERTY_ROOT + 'temperature',
           callback=lambda temp: temperature_label.setText('Temperature: {}°C'.format(temp)))

    def disable_all(self):
        for lamp_controller in self.lamp_controllers:
            lamp_controller.toggle.setChecked(False)

class TLLampWidget(device_widget.DeviceWidget):
    PROPERTY_ROOT = 'scope.tl.lamp.'

    def __init__(self, host, scope, scope_properties, parent=None):
        super().__init__(host, scope, scope_properties, parent)
        self.setWindowTitle('TL Lamp')
        grid_layout = Qt.QGridLayout()
        self.setLayout(grid_layout)
        self.lamp_controller = LampController(self, self.PROPERTY_ROOT[:-1], grid_layout, 0)

class LampWidget(Qt.QWidget):
    @staticmethod
    def can_run(scope):
        return SpectraXWidget.can_run(scope) or TLLampWidget.can_run(scope)

    def __init__(self, host, scope, scope_properties, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Lamp Controller')
        container_layout = Qt.QVBoxLayout()
        self.setLayout(container_layout)
        if TLLampWidget.can_run(scope):
            tl = TLLampWidget(host, scope, scope_properties, self)
            container_layout.addWidget(tl)
        if SpectraXWidget.can_run(scope):
            spx = SpectraXWidget(host, scope, scope_properties, self)
            container_layout.addWidget(spx)

class LampController:
    def __init__(self, widget, name, layout, row):
        toggle = Qt.QCheckBox(name)
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
