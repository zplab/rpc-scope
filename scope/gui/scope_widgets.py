# The MIT License (MIT)
#
# Copyright (c) 2016 WUSTL ZPLAB
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

from PyQt5 import Qt
from . import widget_column_flow_main_window

class WidgetWindow(widget_column_flow_main_window.WidgetColumnFlowMainWindow):
    def __init__(self, scope, scope_properties, widgets, window_title='Scope Widgets', parent=None):
        """Arguments:
            scope, scope_properties: as returned by scope.scope_client.client_main(..).
            widgets: list of widget information dictionaries as defined in build_gui
            parent: defaults to None, which is what you want if WidgetWindow is a top level window."""
        super().__init__(parent)
        self.setWindowTitle(window_title)
        self.action_toolbar = None
        for widget_info in widgets:
            widget_class = widget_info['cls']
            if widget_class.can_run(scope):
                widget = widget_class(scope=scope, scope_properties=scope_properties)
                if isinstance(widget, Qt.QAction):
                    if self.action_toolbar is None:
                        self.action_toolbar = self.addToolBar('Actions')
                    self.action_toolbar.addAction(widget)
                else:
                    self.add_widget(widget, widget_info['docked'], widget_info['start_visible'])
        scope.rebroadcast_properties()

