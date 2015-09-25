# The MIT License (MIT)
#
# Copyright (c) 2015 WUSTL ZPLAB
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

import enum
from PyQt5 import Qt
from . import device_widget

class PT(enum.Enum):
    Bool = 0,
    Int = 1,
    Float = 2,
    Enum = 3,
    IdxEnum = 4

class MicroscopeWidget(device_widget.DeviceWidget):
    PROPERTY_ROOT = 'scope.'
    PROPERTIES = [
        ('stand.active_microscopy_method', PT.Enum, 'stand.available_microscopy_methods'),
        ('nosepiece.position', PT.IdxEnum, 'nosepiece.all_objectives'),
        ('nosepiece.safe_mode', PT.Bool),
        ('nosepiece.immersion_mode', PT.Bool),
        ('il.shutter_open', PT.Bool),
        ('tl.shutter_open', PT.Bool),
        ('il.field_wheel', PT.Enum, 'il.field_wheel_positions'),
        ('il.filter_cube', PT.Enum, 'il.filter_cube_values'),
        ('tl.aperture_diaphragm', PT.Int),
        ('tl.field_diaphragm', PT.Int),
        ('tl.condenser_retracted', PT.Bool),
        ('stage.x', PT.Float),
        ('stage.y', PT.Float),
        ('stage.z', PT.Float)]

    @classmethod
    def can_run(cls, scope):
        # We're good if at least one of our properties can be read.  Properties that can not be read
        # when the widget is created are not shown in the GUI.
        for ppath, *_ in prop_tuple in cls.PROPERTIES:
            C = scope
            ppathcs = ppath.split('.')
            try:
                for ppathc in ppathcs:
                    C = getattr(C, ppathc)
            except AttributeError:
                continue
            return True
        return False

    def __init__(self, scope, scope_properties, parent=None):
        super().__init__(scope, scope_properties, parent)
        self.setWindowTitle('Microscope')
        self.setLayout(Qt.QGridLayout())
        self.scope = scope
        self.widget_makers = {
            PT.Bool : self.make_bool_widget,
            PT.Int : self.make_numeric_widget,
            PT.Float : self.make_numeric_widget,
            PT.Enum : self.make_enum_widget,
            PT.IdxEnum : self.make_idx_enum_widget}
        for ptuple in self.PROPERTIES:
            self.make_widgets_for_property(ptuple)

    def make_widgets_for_property(self, ptuple):
        if ptuple[1] is not PT.Bool:
            return
        layout = self.layout()
        row = layout.rowCount()
        label = Qt.QLabel(ptuple[0] + ':')
        layout.addWidget(label, row, 0)
        widget = self.widget_makers[ptuple[1]](ptuple)
        layout.addWidget(widget, row, 1)
        return label, widget

    def make_bool_widget(self, ptuple):
        widget = Qt.QCheckBox()
        update = self.subscribe(self.PROPERTY_ROOT + ptuple[0], callback=widget.setChecked)
        print(self.PROPERTY_ROOT + ptuple[0])
        if update is None:
            raise TypeError('{} is not a writable property!'.format(property))
        def changed(value):
            try:
                update(value)
            except rpc_client.RPCError as e:
                error = 'Could not set {} ({}).'.format(property, e.args[0])
                Qt.QMessageBox.warning(self, 'Invalid Value', error)
        widget.toggled.connect(changed)
        return widget

    def make_numeric_widget(self, ptuple):
        pass

    def make_enum_widget(self, ptuple):
        pass

    def make_idx_enum_widget(self, ptuple):
        pass
