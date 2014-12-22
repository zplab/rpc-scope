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
# Authors: Erik Hvatum <ice.rikh@gmail.com>

from .device_widget import DeviceWidget
from PyQt5 import Qt

class SpectraX_Widget(DeviceWidget):
    class ColorControlSet:
        def __init__(self, toggle, slider, spin_box, set_enable, set_intensity):
            self.toggle = toggle
            self.slider = slider
            self.spin_box = spin_box
            self.set_enable = set_enable
            self.set_intensity = set_intensity
            # Values from most recent property change notifications
            self.enabled = None
            self.intensity = None

    def __init__(self, scope, scope_properties, device_path='scope.il.spectra_x', parent=None, rebroadcast_on_init=True, foo='bar'):
        self.foo = foo
        self.updating_gui = False
        super().__init__(scope, scope_properties, device_path, None, parent)
        self.setWindowTitle('Spectra X')
        lamps = sorted(((k, v[0]) for k, v in scope.il.spectra_x.lamp_specs.items()), key=lambda kv:kv[1], reverse=True)
        self.setLayout(Qt.QVBoxLayout())
        self.grid_layout = Qt.QGridLayout()
        self.layout().addLayout(self.grid_layout)
        self.color_control_sets = {}
        for row, (color, wavelength) in enumerate(lamps):
            self.subscribe(color, 'intensity')
            self.subscribe(color, 'enabled')
            ccs = self.ColorControlSet(Qt.QCheckBox(color),
                                       Qt.QSlider(Qt.Qt.Horizontal),
                                       Qt.QSpinBox(),
                                       lambda enable, color=color, setter=getattr(self.device, 'lamp_enable'): setter(**{color : enable}),
                                       lambda intensity, color=color, setter=getattr(self.device, 'lamp_intensity'): setter(**{color : intensity}))
            ccs.toggle.toggled.connect(lambda enabled, prop_path='{}.{}.enabled'.format(self.device_path, color), self=self: self.property_change_slot(prop_path, enabled, False))
            ccs.slider.setRange(0, 255)
            ccs.slider.setSingleStep(1)
            ccs.slider.setPageStep(5)
            ccs.slider.setValue(0)
            ccs.slider.valueChanged.connect(lambda intensity, prop_path='{}.{}.intensity'.format(self.device_path, color), self=self: self.property_change_slot(prop_path, intensity, False))
            ccs.spin_box.setRange(0, 255)
            ccs.spin_box.setSingleStep(1)
            ccs.spin_box.setValue(0)
            ccs.spin_box.valueChanged.connect(lambda intensity, prop_path='{}.{}.intensity'.format(self.device_path, color), self=self: self.property_change_slot(prop_path, intensity, False))
            self.grid_layout.addWidget(ccs.toggle, row, 0)
            self.grid_layout.addWidget(ccs.slider, row, 1)
            self.grid_layout.addWidget(ccs.spin_box, row, 2)
            self.color_control_sets[color] = ccs
        self.bottom_layout = Qt.QHBoxLayout()
        self.layout().addLayout(self.bottom_layout)
        self.disable_all_button = Qt.QPushButton('Disable All')
        self.bottom_layout.addWidget(self.disable_all_button)
        self.disable_all_button.clicked.connect(self.disable_all_slot)
        self.temperature_label = Qt.QLabel('Temperature: (unknown)')
        self.bottom_layout.addWidget(self.temperature_label)
        self.subscribe('temperature')
        self._ChangeSignalFromPropertyClient.connect(self.property_change_slot, Qt.Qt.QueuedConnection)
        if rebroadcast_on_init:
            self.scope.rebroadcast_properties()

    def property_change_slot(self, prop_path, prop_value, is_prop_update=True):
        if not self.updating_gui: # Avoid recursive valueChanged calls and looping changes caused by running ahead of property change notifications
            self.updating_gui = True
            if prop_path not in self.subscribed_prop_paths:
                raise RuntimeError('Called for property "{}", which is not associated one of those of this device (all of which begin with "{}.").'.format(name, self.device_path))
            prop_path_parts = prop_path.split('.')
            if prop_path_parts[-1] == 'temperature':
                self.temperature_label.setText('Temperature: {}ºC'.format(prop_value))
            else:
                ccs = self.color_control_sets[prop_path_parts[-2]]
                if prop_path_parts[-1] == 'enabled':
                    if ccs.toggle.isChecked() != prop_value:
                        ccs.toggle.setChecked(prop_value)
                    if is_prop_update:
                        ccs.enabled = prop_value
                    else:
                        if ccs.enabled != prop_value:
                            ccs.set_enable(prop_value)
                elif prop_path_parts[-1] == 'intensity':
                    if ccs.slider.value() != prop_value:
                        ccs.slider.setValue(prop_value)
                    if ccs.spin_box.value() != prop_value:
                        ccs.spin_box.setValue(prop_value)
                    if is_prop_update:
                        ccs.intensity = prop_value
                    else:
                        if ccs.intensity != prop_value:
                            ccs.set_intensity(prop_value)
                            ccs.intensity = prop_value
            self.updating_gui = False

    def disable_all_slot(self):
        for color, ccs in self.color_control_sets.items():
            ccs.set_enable(False)
