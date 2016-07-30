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
# Authors: Erik Hvatum <ice.rikh@gmail.com>

from PyQt5 import Qt
from . import widget_column_flow_main_window

from . import andor_camera_widget
from . import lamp_widget
from . import scope_viewer_widget
from . import microscope_widget
from . import stage_pos_table_widget
from . import joypad_input_widget

WIDGETS = {
    'camera': andor_camera_widget.AndorCameraWidget,
    'lamps': lamp_widget.LampWidget,
    'viewer': scope_viewer_widget.ScopeViewerWidget,
    'microscope': microscope_widget.MicroscopeWidget,
    'stage_pos_table': stage_pos_table_widget.StagePosTableWidget,
    'joypad_input': joypad_input_widget.JoypadInputWidget
}

class WidgetWindow(widget_column_flow_main_window.WidgetColumnFlowMainWindow):
    def __init__(
            self,
            host, scope, scope_properties,
            names_of_desired_widgets=('all',), show_cant_run_warning=True,
            window_title='Scope Widgets', parent=None):
        """Arguments:
        * host: Hostname or IP address of scope server.
        * scope: scope.scope.Scope object instance - the first element of the tuple returned by
        scope.scope_client.client_main(..).
        * scope_properties: scope.simple_rpc.property_client.ZMQClient - the second element of the tuple returned by
        scope.scope_client.client_main(..).
        * names_of_desired_widgets: Either 'all' or an iterable of any subset of list(scope.gui.scope_widgets.WIDGETS.keys()).
        For example, desired_widgets=('camera', 'viewer').
        * show_cant_run_warning: If True (the default), display a warning dialog with the names any of the desired widgets
        reporting that they can not run (IE, their .can_run(..) static/class method returns False).
        * window_title: defaults to 'Scope Widgets'.
        * parent: defaults to None, which is what you want if WidgetWindow is a top level window."""
        super().__init__(parent)
        self.setWindowTitle(window_title)
        self.names_to_widgets = {}
        self.widgets_to_names = {}
        if 'all' in names_of_desired_widgets:
            wncs = WIDGETS
        else:
            wncs = {name: WIDGETS[name] for name in names_of_desired_widgets}
        desired_but_cant_run = []
        for wn in sorted(wncs.keys()):
            wc = wncs[wn]
            if wc.can_run(scope):
                self.add_widget(wn, wc(host=host, scope=scope, scope_properties=scope_properties), wn=='viewer')
            else:
                desired_but_cant_run.append(wn)
        scope.rebroadcast_properties()
        if show_cant_run_warning and desired_but_cant_run:
            Qt.QMessageBox.warning(self, 'WidgetWindow Warning', 'Scope can not currently run {}.  (Hardware not turned on?)'.format(
                desired_but_cant_run if len(desired_but_cant_run) == 1 else ', '.join(desired_but_cant_run[:-1]) + ', or ' + desired_but_cant_run[-1]
            ))

    def add_widget(self, name, widget, floating=False):
        assert not hasattr(self, name)
        assert name not in self.names_to_widgets
        assert widget not in self.widgets_to_names
        super().add_widget(widget.qt_object if hasattr(widget, 'qt_object') else widget, floating)
        setattr(self, name, widget)
        self.names_to_widgets[name] = widget
        self.widgets_to_names[widget] = name
        if isinstance(widget, Qt.QAction):
            if not hasattr(self, 'action_toolbar'):
                self.action_toolbar = self.addToolBar('Actions')
            self.action_toolbar.addAction(widget)

    def remove_widget(self, widget_or_name):
        if isinstance(widget_or_name, str):
            name = widget_or_name
            widget = self.names_to_widgets[widget_or_name]
        else:
            name = self.widgets_to_names[widget_or_name]
            widget = widget_or_name
        super().remove_widget(widget.qt_object if hasattr(widget, 'qt_object') else widget)
        delattr(self, name)
        del self.widgets_to_names[widget]
        del self.names_to_widgets[name]
        if isinstance(widget, Qt.QAction):
            self.action_toolbar.removeAction(widget)

    def on_pop_request(self, container, out):
        super().on_pop_request(container, out)
        if not out:
            l = self._w.layout()
            l.itemList.sort(key=lambda i: i.widget().windowTitle())
            l.doLayout(self._w.rect(), False)