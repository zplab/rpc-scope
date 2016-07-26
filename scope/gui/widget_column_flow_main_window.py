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

class WidgetColumnFlowMainWindow(Qt.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.widgets = []
        self._w = Qt.QWidget()
        self._w.setLayout(Qt.QHBoxLayout())
        self.setCentralWidget(self._w)
        self.widgets_to_containers = {}
        self.visibility_toolbar = self.addToolBar('Visibility')

    def add_widget(self, widget):
        assert widget not in self.widgets
        container = FloatableHideableWidgetContainer(widget)
        self.widgets_to_containers[widget] = container
        self.widgets.append(widget)
        self._w.layout().addWidget(container)
        container.pop_request_signal.connect(self.on_pop_request)
        container.visibility_change_signal.connect(self.on_visibility_change_signal)
        self.visibility_toolbar.addAction(container.visibility_change_action)

    def remove_widget(self, widget):
        assert widget in self.widgets
        container = self.widgets_to_containers[widget]
        container.pop_request_signal.disconnect(self.on_pop_request)
        container.visibility_change_signal.disconnect(self.on_visibility_change_signal)
        if container.is_visible and not container.is_floating:
            self._w.layout().removeWidget(container)
        container.deleteLater()
        del self.widgets_to_containers[widget]
        del self.widgets[self.widgets.index(widget)]
        self.visibility_toolbar.removeAction(container.visibility_change_action)

    def reflow(self):
        pass

    def on_pop_request(self, container, out):
        if out:
            container.setParent(None)
            container.show()
        else:
            self._w.layout().addWidget(container)

    def on_visibility_change_signal(self, container, visible):
        container.setVisible(visible)

    def closeEvent(self, e):
        for container in self.widgets_to_containers.values():
            if container.is_floating:
                container.close()

class FloatableHideableWidgetContainer(Qt.QWidget):
    pop_request_signal = Qt.pyqtSignal(Qt.QWidget, bool)
    visibility_change_signal = Qt.pyqtSignal(Qt.QWidget, bool)

    def __init__(self, contained_widget):
        super().__init__()
        self.contained_widget = contained_widget
        l = Qt.QVBoxLayout()
        self.setLayout(l)
        self.pop_button = Qt.QPushButton('\N{NORTH EAST ARROW}')
        self.pop_button.setCheckable(True)
        self.pop_button.setChecked(False)
        self.pop_button.clicked.connect(self.on_popout_button_clicked)
        if hasattr(contained_widget, 'embed_widget_flow_pop_button'):
            contained_widget.embed_widget_flow_pop_button(self.pop_button)
            l.addWidget(contained_widget)
        else:
            self.pop_groupbox = Qt.QGroupBox()
            l.addWidget(self.pop_groupbox)
            ll = Qt.QHBoxLayout()
            ll.setContentsMargins(0,0,0,0)
            self.pop_groupbox.setLayout(ll)
            ll.addSpacerItem(Qt.QSpacerItem(0, 0, Qt.QSizePolicy.Expanding))
            ll.addWidget(self.pop_button)
            l.addWidget(contained_widget)
            l.addSpacerItem(Qt.QSpacerItem(0, 0, Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Expanding))
        self.visibility_change_action = Qt.QAction(contained_widget.windowTitle(), self)
        self.visibility_change_action.setCheckable(True)
        self.visibility_change_action.setChecked(True)
        self.visibility_change_action.toggled.connect(self.on_visibility_change_action_toggled)
        contained_widget.windowTitleChanged.connect(self.visibility_change_action.setText)

    def on_popout_button_clicked(self, out):
        self.pop_request_signal.emit(self, out)

    def on_visibility_change_action_toggled(self, visible):
        self.visibility_change_signal.emit(self, visible)

    def closeEvent(self, e):
        super().closeEvent(e)
        if e.isAccepted():
            self.visibility_change_action.setChecked(False)

    def showEvent(self, e):
        super().showEvent(e)
        if e.isAccepted():
            self.visibility_change_action.setChecked(True)

    @property
    def is_floating(self):
        return self.pop_button.isChecked()

    @property
    def is_visible(self):
        return self.visibility_change_action.isChecked()