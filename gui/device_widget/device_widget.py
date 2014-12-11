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

import os
from pathlib import Path
from PyQt5 import Qt, uic

class DeviceWidget(Qt.QWidget):
    def __init__(self, scope, scope_properties, device_path, py_ui_fpath, parent):
        super().__init__(parent)
        self.scope = scope
        self.scope_properties = scope_properties

        if py_ui_fpath is not None:
            ui_sfpath = str(py_ui_fpath)
            ui_fpath = Path(py_ui_fpath)
            if ui_sfpath.endswith('.py'):
                # Child class is being lazy and gave us its __file__ variable rather than its .ui filename/path
                ui_fpath = ui_fpath.parent / (ui_fpath.parts[-1][:-3] + '.ui')
                ui_sfpath = str(ui_fpath)
            # Note that uic.loadUiType(..) returns a tuple containing two class types (the form class and the Qt base
            # class).  The line below instantiates the form class.  It is assumed that the .ui file resides in the same
            # directory as this .py file.
            print(ui_sfpath)
            self.ui = uic.loadUiType(ui_sfpath)[0]()
            self.ui.setupUi(self)
