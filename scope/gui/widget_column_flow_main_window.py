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
        self._w.setLayout(FlowLayout())
        self.setCentralWidget(self._w)
        self.widgets_to_containers = {}
        self.visibility_toolbar = self.addToolBar('Visibility')

    def add_widget(self, widget, floating=False, visible=True):
        assert widget not in self.widgets
        if isinstance(widget, Qt.QWidget):
            container = FloatableHideableWidgetContainer(widget)
            self.widgets_to_containers[widget] = container
            self.widgets.append(widget)
            if floating:
                container.pop_button.setChecked(True)
                container.setParent(None)
                if visible:
                    container.show()
            elif visible:
                self._w.layout().addWidget(container)
            container.pop_request_signal.connect(self.on_pop_request)
            container.visibility_change_signal.connect(self.on_visibility_change_signal)
            self.visibility_toolbar.addAction(container.visibility_change_action)
        else:
            self.widgets.append(widget)

    def remove_widget(self, widget):
        assert widget in self.widgets
        if isinstance(widget, Qt.QWidget):
            container = self.widgets_to_containers[widget]
            container.pop_request_signal.disconnect(self.on_pop_request)
            container.visibility_change_signal.disconnect(self.on_visibility_change_signal)
            if container.is_visible and not container.is_floating:
                self._w.layout().removeWidget(container)
            container.deleteLater()
            del self.widgets_to_containers[widget]
            del self.widgets[self.widgets.index(widget)]
            self.visibility_toolbar.removeAction(container.visibility_change_action)
        else:
            del self.widgets[self.widgets.index(widget)]

    def on_pop_request(self, container, out):
        if out:
            container.setParent(None)
            container.show()
        else:
            self._w.layout().addWidget(container)

    def on_visibility_change_signal(self, container, visible):
        container.setVisible(visible)
        if container.is_floating and container.parent() is not None:
            container.setParent(None)
            container.show()

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
        margins = list(l.getContentsMargins())
        margins[1] = 0
        l.setContentsMargins(*margins)
        self.setLayout(l)
        self.pop_button = Qt.QPushButton('\N{NORTH EAST ARROW}')
        self.pop_button.setCheckable(True)
        self.pop_button.setChecked(False)
        self.pop_button.setFocusPolicy(Qt.Qt.NoFocus)
        self.pop_button.clicked.connect(self.on_popout_button_clicked)
        if hasattr(contained_widget, 'embed_widget_flow_pop_button'):
            contained_widget.embed_widget_flow_pop_button(self.pop_button)
            l.addWidget(contained_widget)
        else:
            self.pop_frame = Qt.QFrame()
            self.pop_frame.setFrameStyle(Qt.QFrame.StyledPanel | Qt.QFrame.Plain)
            self.pop_frame.setBackgroundRole(Qt.QPalette.Shadow)
            self.pop_frame.setAutoFillBackground(True)
            self.pop_frame_title_label = Qt.QLabel()
            f = self.pop_frame_title_label.font()
            f.setPointSizeF(f.pointSize() * 1.5)
            f.setBold(True)
            self.pop_frame_title_label.setAlignment(Qt.Qt.AlignLeft | Qt.Qt.AlignVCenter)
            self.pop_frame_title_label.setFont(f)
            l.addWidget(self.pop_frame)
            ll = Qt.QHBoxLayout()
            ll.setContentsMargins(1,1,1,1)
            self.pop_frame.setLayout(ll)
            ll.addWidget(self.pop_frame_title_label)
            ll.addSpacerItem(Qt.QSpacerItem(0, 0, Qt.QSizePolicy.Expanding))
            ll.addWidget(self.pop_button)
            l.addWidget(contained_widget)
        self.visibility_change_action = Qt.QAction(contained_widget.windowTitle(), self)
        self.visibility_change_action.setCheckable(True)
        self.visibility_change_action.setChecked(False)
        self.visibility_change_action.toggled.connect(self.on_visibility_change_action_toggled)
        contained_widget.windowTitleChanged.connect(self.on_contained_widget_window_title_changed)
        self.on_contained_widget_window_title_changed(contained_widget.windowTitle())
        if not hasattr(contained_widget, 'embed_widget_flow_pop_button'):
            self.pop_frame.setSizePolicy(Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Fixed)

    def on_popout_button_clicked(self, out):
        # Uncomment to hide popout-area title when floating
        # if hasattr(self, 'pop_frame_title_label'):
        #     self.pop_frame_title_label.setVisible(not out)
        self.pop_request_signal.emit(self, out)

    def on_visibility_change_action_toggled(self, visible):
        self.visibility_change_signal.emit(self, visible)

    def on_contained_widget_window_title_changed(self, t):
        self.visibility_change_action.setText(t)
        self.setWindowTitle(t)
        if hasattr(self, 'pop_frame_title_label'):
            self.pop_frame_title_label.setText("<font color='white'>{}</font>".format(t))

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

# Adapted from Qt Docs / Qt Widgets / Flow Layout Example
class FlowLayout(Qt.QLayout):
    def __init__(self, margin=-1, hSpacing=-1, vSpacing=-1, default_height=1800):
        super().__init__()
        self.m_hSpace = hSpacing
        self.m_vSpace = vSpacing
        self.default_height = default_height
        self.setContentsMargins(margin, margin, margin, margin)
        self.itemList = []

    def addItem(self, item):
        self.itemList.append(item)

    def horizontalSpacing(self):
        if self.m_hSpace >= 0:
            return self.m_hSpace
        else:
            return self.smartSpacing(Qt.QStyle.PM_LayoutHorizontalSpacing)

    def verticalSpacing(self):
        if self.m_vSpace >= 0:
            return self.m_vSpace
        else:
            return self.smartSpacing(Qt.QStyle.PM_LayoutVerticalSpacing)

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList[index]

    def takeAt(self, index):
        if 0 <= index < len(self.itemList):
            v = self.itemList[index]
            del self.itemList[index]

    def expandingDirections(self):
        return 0

    def hasWidthForHeight(self):
        return True

    def widthForHeight(self, height):
        return self.doLayout(Qt.QRect(0, 0, 0, height), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return Qt.QSize(self.doLayout(Qt.QRect(0, 0, 0, self.default_height), True), self.default_height)

    def minimumSize(self):
      size = Qt.QSize()
      for item in self.itemList:
          size = size.expandedTo(item.minimumSize())
      size += Qt.QSize(2*self.spacing(), 2*self.spacing())
      return size

    def doLayout(self, rect, test_only):
        x, y = rect.x(), rect.y()
        width = height = 0
        column = []
        for item_idx, item in enumerate(self.itemList):
            next_item = self.itemList[item_idx + 1] if item_idx + 1 < len(self.itemList) else None
            next_y = y + item.sizeHint().height()
            if next_y > rect.bottom() and width > 0:
                y = rect.y()
                x = x + width + self.spacing()
                next_y = y + item.sizeHint().height()
                width = 0
            if not test_only:
                item.setGeometry(Qt.QRect(Qt.QPoint(x, y), item.sizeHint()))
                column.append(item)
                height += item.sizeHint().height()
                if next_item is None or next_y + next_item.sizeHint().height() > rect.bottom():
                    actual_width = 0
                    for citem in column:
                        actual_width = max(actual_width, citem.widget().sizeHint().width())
                    # gap = (rect.height() - height) / (len(column) + 1)
                    for citem_idx, citem in enumerate(column):
                        r = citem.geometry()
                        citem.setGeometry(Qt.QRect(
                            r.left(),
                            r.top() + citem_idx,# * gap,
                            actual_width,
                            r.height()
                        ))
                    column = []
                    height = 0
            y = next_y
            width = max(width, item.sizeHint().width())
        return x + width - rect.x()

    def smartSpacing(self, pm):
        parent = self.parent()
        if parent is None:
            return -1
        elif parent.isWidgetType():
            return parent.style().pixelMetric(pm, None, parent)
        else:
            return parent.spacing()