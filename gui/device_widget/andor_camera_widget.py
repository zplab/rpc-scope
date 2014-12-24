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
from ...simple_rpc.rpc_client import RPCError
import weakref

class AndorCameraWidget(DeviceWidget):
    def __init__(self, scope, scope_properties, device_path='scope.camera', parent=None, rebroadcast_on_init=True):
        super().__init__(scope, scope_properties, device_path, None, parent)
        self.setWindowTitle('Andor Camera ({})'.format(self.device.model_name))
        layout = Qt.QGridLayout()
        self.setLayout(layout)
        row = 0
        property_widget_set_types = {'Bool' : self.BoolPropertyWidgetSet,
                                     'String' : self.ROStringPropertyWidgetSet,
                                     'Int' : self.IntPropertyWidgetSet,
                                     'Float' : self.FloatPropertyWidgetSet}
        self.property_widget_sets = {}
        for prop_name, prop_stuff in sorted(self.device.property_types_and_extrema.items()):
            if type(prop_stuff) is str:
                prop_type = prop_stuff
                prop_extrema = None
            else:
                prop_type = prop_stuff[0]
                prop_extrema = prop_stuff[1]
            try:
                pwst = property_widget_set_types[prop_type]
            except KeyError:
                continue
            self.subscribe(prop_name)
            self.property_widget_sets[prop_name] = pwst(self, layout, row, prop_name, prop_extrema)
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

    ### Helper classes ###

    class PropertyWidgetSet:
        def __init__(self, andor_camera_widget, layout, row, prop_name):
            self.prop_name = prop_name
            self.name_label = Qt.QLabel(prop_name + ':')
            self.device = andor_camera_widget.device
            self.andor_camera_widget_weakref = weakref.ref(andor_camera_widget)
            layout.addWidget(self.name_label, row, 0)
            # Value from most recent property change notification
            self.value = None

        def update(self, prop_value, is_prop_update):
            raise NotImplementedError('pure virtual method called')

    class BoolPropertyWidgetSet(PropertyWidgetSet):
        def __init__(self, andor_camera_widget, layout, row, prop_name, _):
            pass

    class ROStringPropertyWidgetSet(PropertyWidgetSet):
        # Note that all AT_String properties are currently read-only
        def __init__(self, andor_camera_widget, layout, row, prop_name, _):
            super().__init__(andor_camera_widget, layout, row, prop_name)
            self.value_label = Qt.QLineEdit()
            self.value_label.setReadOnly(True)
            layout.addWidget(self.value_label, row, 1)
            self.name_label.setBuddy(self.value_label)

        def update(self, prop_value, is_prop_update):
            self.value_label.setText(prop_value)
            self.value = prop_value

    class IntPropertyWidgetSet(PropertyWidgetSet):
        def __init__(self, andor_camera_widget, layout, row, prop_name, prop_extrema):
            super().__init__(andor_camera_widget, layout, row, prop_name)
            self.is_ro = prop_extrema is None
            if self.is_ro:
                self.value_label = Qt.QLineEdit()
                self.value_label.setReadOnly(True)
                layout.addWidget(self.value_label, row, 1)
                self.name_label.setBuddy(self.value_label)
            else:
                self.value_spin_box = Qt.QSpinBox()
                self.value_spin_box.setRange(prop_extrema[0], prop_extrema[1])
                layout.addWidget(self.value_spin_box, row, 1)
                self.name_label.setBuddy(self.value_spin_box)
                self.value_spin_box.valueChanged.connect(lambda v,
                                                         pcs=andor_camera_widget.property_change_slot,
                                                         pp=andor_camera_widget.device_path+'.'+prop_name:
                                                            pcs(pp, v, False))

        def update(self, prop_value, is_prop_update):
            if self.is_ro:
                self.value_label.setText(str(prop_value))
                self.value = prop_value
            else:
                if self.value_spin_box.value() != prop_value:
                    self.value_spin_box.setValue(prop_value)
                if is_prop_update:
                    self.value = prop_value
                else:
                    if self.value != prop_value:
                        try:
                            setattr(self.device, self.prop_name, prop_value)
                            self.value = prop_value
                        except RPCError as e:
                            self.value_spin_box.setValue(self.value)
                            if e.args[0].find('AndorError: OUTOFRANGE') != -1:
                                s  = 'Given the current camera state, '
                                s += self.prop_name
                                s += ' '
                                try:
                                    range_ = getattr(self.device, self.prop_name+'_range')
                                    if range_[0] == range_[1]:
                                        if range_[0] is None:
                                            s += 'must be in an UNKNOWN range (sorry).'
                                        else:
                                            s += 'is only permitted to be {}.'.format(range_[0])
                                    else:
                                        s += 'must be in the range [{}, {}].'.format('UNKNOWN' if range_[0] is None else range_[0],
                                                                            'UNKNOWN' if range_[1] is None else range_[1])
                                except:
                                    s += 'must be in the range (FAILED TO DETERMINE ACCEPTABLE VALUES).'
                            elif e.args[0].find('AndorError: NOTWRITABLE'):
                                s  = 'Given the current camera state, '
                                s += self.prop_name
                                s += ' can not be modified.'
                            else:
                                s = 'Failed to set {} property.'.format(self.prop_name)
                            Qt.QMessageBox.warning(self.andor_camera_widget_weakref(), 'Range Error', s)

    class FloatPropertyWidgetSet(PropertyWidgetSet):
        def __init__(self, andor_camera_widget, layout, row, prop_name, prop_extrema):
            super().__init__(andor_camera_widget, layout, row, prop_name)
            self.is_ro = prop_extrema is None
            if self.is_ro:
                self.value_label = Qt.QLineEdit()
                self.value_label.setReadOnly(True)
                layout.addWidget(self.value_label, row, 1)
                self.name_label.setBuddy(self.value_label)
            else:
                self.value_text_box = Qt.QLineEdit()
                layout.addWidget(self.value_text_box, row, 1)
                self.name_label.setBuddy(self.value_text_box)
                self.value_text_box.editingFinished.connect(self.value_text_box_editing_finished_slot)
                self.value_text_box.returnPressed.connect(self.value_text_box_editing_finished_slot)

        def value_text_box_editing_finished_slot(self):
            prop_value_string = self.value_text_box.text()
            try:
                prop_value = float(prop_value_string)
            except ValueError as e:
                Qt.QMessageBox.warning(self.andor_camera_widget_weakref(), 'Value Error', e.args[0])
                prop_value = None
            if prop_value is not None:
                acw = self.andor_camera_widget_weakref()
                acw.property_change_slot(acw.device_path+'.'+self.prop_name, prop_value, False)

        def update(self, prop_value, is_prop_update):
            if self.is_ro:
                self.value_label.setText(str(prop_value))
                self.value = prop_value
            else:
                prop_value_string = str(prop_value)
                write_to_value_text_box = True
                try:
                    if float(self.value_text_box.text()) == prop_value:
                        write_to_value_text_box = False
                except ValueError:
                    pass
                if write_to_value_text_box:
                    self.value_text_box.setText(str(prop_value))
                if is_prop_update:
                    self.value = prop_value
                else:
                    if self.value != prop_value:
                        try:
                            setattr(self.device, self.prop_name, prop_value)
                            self.value = prop_value
                        except RPCError as e:
                            self.value_text_box.setText(str(self.value))
                            if e.args[0].find('AndorError: OUTOFRANGE') != -1:
                                s  = 'Given the current camera state, '
                                s += self.prop_name
                                s += ' '
                                try:
                                    range_ = getattr(self.device, self.prop_name+'_range')
                                    if range_[0] == range_[1]:
                                        if range_[0] is None:
                                            s += 'must be in an UNKNOWN range (sorry).'
                                        else:
                                            s += 'is only permitted to be {}.'.format(range_[0])
                                    else:
                                        s += 'must be in the range [{}, {}].'.format('UNKNOWN' if range_[0] is None else range_[0],
                                                                            'UNKNOWN' if range_[1] is None else range_[1])
                                except:
                                    s += 'must be in the range (FAILED TO DETERMINE ACCEPTABLE VALUES).'
                            elif e.args[0].find('AndorError: NOTWRITABLE'):
                                s  = 'Given the current camera state, '
                                s += self.prop_name
                                s += ' can not be modified.'
                            else:
                                s = 'Failed to set {} property.'.format(self.prop_name)
                            Qt.QMessageBox.warning(self.andor_camera_widget_weakref(), 'Range Error', s)
