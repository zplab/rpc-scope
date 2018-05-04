# This code is licensed under the MIT License (see LICENSE file for details)

from . import device_widget
from PyQt5 import Qt

class IncubatorWidget(device_widget.DeviceWidget):
    @staticmethod
    def can_run(scope):
        return hasattr(scope, 'temperature_controller') and hasattr(scope, 'humidity_controller')

    def __init__(self, scope, parent=None):
        super().__init__(scope, parent)
        self.setWindowTitle('Incubator')
        layout = Qt.QGridLayout()
        self.setLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setVerticalSpacing(4)
        self.add_row(0, 'Temperature', '°C', 'scope.humidity_controller.temperature', 'scope.temperature_controller.target_temperature', 10, 40)
        self.add_row(1, 'Humidity', '%', 'scope.humidity_controller.humidity', 'scope.humidity_controller.target_humidity', 0, 99)

    def add_row(self, row, name, unit, value_property, target_property, range_low, range_high):
        layout = self.layout()
        target_label = Qt.QLabel('Target {}:'.format(name))
        target_label.setAlignment(Qt.Qt.AlignRight | Qt.Qt.AlignVCenter)
        #target_label.setSizePolicy(Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Expanding)
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
        self.subscribe(value_property, callback=lambda value: label.setText('{}\t{}: {} {}'.format(unit, name, value, unit)), readonly=True)

