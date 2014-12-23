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

class AndorCameraWidget(DeviceWidget):
    class PropertyWidgetSet:
        def __init__(self, andor_camera_widget, layout, row, prop_name):
            self.name_label = Qt.QLabel(prop_name + ':')
            layout.addWidget(self.name_label, row, 0)
            # Value from most recent property change notification
            self.value = None

        def update(self, prop_value, is_prop_update):
            raise NotImplementedError('pure virtual method called')

    class ROStringPropertyWidgetSet(PropertyWidgetSet):
        # Note that all AT_String properties are currently read-only
        def __init__(self, andor_camera_widget, layout, row, prop_name):
            super().__init__(andor_camera_widget, layout, row, prop_name)
            self.value_label = Qt.QLabel()
            layout.addWidget(self.value_label, row, 1)

        def update(self, prop_value, is_prop_update):
            self.value_label.setText(prop_value)
            self.value = prop_value

    def __init__(self, scope, scope_properties, device_path='scope.camera', parent=None, rebroadcast_on_init=True):
        super().__init__(scope, scope_properties, device_path, None, parent)
        self.setWindowTitle('Andor Camera ({})'.format(self.device.model_name))
        layout = Qt.QGridLayout()
        self.setLayout(layout)
        row = 0
        property_widget_set_types = {'String' : self.ROStringPropertyWidgetSet}
        self.property_widget_sets = {}
        for prop_name, prop_type in sorted(self.device.property_types.items()):
            try:
                pwst = property_widget_set_types[prop_type]
            except KeyError:
                continue
            self.subscribe(prop_name)
            self.property_widget_sets[prop_name] = pwst(self, layout, row, prop_name)
            row += 1
        self._ChangeSignalFromPropertyClient.connect(self.property_change_slot, Qt.Qt.QueuedConnection)
        if rebroadcast_on_init:
            self.scope.rebroadcast_properties()

    def property_change_slot(self, prop_path, prop_value, is_prop_update=True):
        self.property_change_slot_verify_subscribed(prop_path)
        if not self.updating_gui: # Avoid recursive valueChanged calls and looping changes caused by running ahead of property change notifications
            try:
                self.updating_gui = True
                prop_path_parts = prop_path.split('.')
                self.property_widget_sets[prop_path_parts[-1]].update(prop_value, is_prop_update)
            finally:
                self.updating_gui = False
