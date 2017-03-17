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
# Author: Zach Pincus <zpincus@wustl.edu>


from . import device_widget
from PyQt5 import Qt

class IncubatorWidget(device_widget.DeviceWidget):
    @staticmethod
    def can_run(scope):
        return hasattr(scope, 'temperature_controller') and hasattr(scope, 'humidity_controller')

    def __init__(self, scope, scope_properties, parent=None):
        super().__init__(scope, scope_properties, parent)
        self.setWindowTitle('Incubator')
        self.setLayout(Qt.QGridLayout())
        self.add_row(0, 'Temperature', '°C', 'scope.humidity_controller.temperature', 'scope.temperature_controller.target_temperature', 10, 40)
        self.add_row(1, 'Humidity', '%', 'scope.humidity_controller.humidity', 'scope.humidity_controller.target_humidity', 0, 99)

    def add_row(self, row, name, unit, value_property, target_property, range_low, range_high):
        layout = self.layout()
        target_label = Qt.QLabel('Target {}:'.format(name))
        target_label.setAlignment(Qt.Qt.AlignRight)
        layout.addWidget(target_label, row, 0)
        target = Qt.QLineEdit()
        target.setValidator(Qt.QDoubleValidator(range_low, range_high, 1, parent=self))
        update = self.subscribe(target_property, callback=lambda value: target.setText(str(value)))
        def editing_finished():
            try:
                value = float(target.text())
                update(value)
            except Exception as e:
                Qt.QMessageBox.warning(self, 'Could not set {}'.format(name), e.args[0])
        target.editingFinished.connect(editing_finished)
        layout.addWidget(target, row, 1)
        label = Qt.QLabel('{}\t{}: - {}'.format(unit, name, unit))
        layout.addWidget(label, row, 2)
        self.subscribe(value_property, callback=lambda value: label.setText('{}\t{}: {} {}'.format(unit, name, value, unit)))

