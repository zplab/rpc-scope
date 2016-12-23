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
        self.containers = []
        self._w = Qt.QWidget()
        self._w.setLayout(FlowLayout())
        self.setCentralWidget(self._w)
        self.visibility_toolbar = self.addToolBar('Visibility')

    def add_widget(self, widget, docked=True, visible=True):
        container = HideableWidgetContainer(widget, docked)
        container.setVisible(visible)
        self.containers.append(container)
        if docked:
            self._w.layout().addWidget(container)

        else:
            container.setParent(None)
        self.visibility_toolbar.addAction(container.visibility_change_action)

    def on_pop_request(self, container, out):
        if out:
            container.setParent(None)
            container.show()
        else:
            self._w.layout().addWidget(container)

    def closeEvent(self, e):
        for container in self.containers:
            if not container.docked:
                container.close()

class HideableWidgetContainer(Qt.QWidget):
    def __init__(self, contained_widget, docked):
        super().__init__()
        self.contained_widget = contained_widget
        l = Qt.QVBoxLayout()
        margins = list(l.getContentsMargins())
        margins[1] = 0
        l.setContentsMargins(*margins)
        self.setLayout(l)
        self.docked = docked
        if docked:
            self.frame = Qt.QFrame()
            self.frame.setFrameStyle(Qt.QFrame.StyledPanel | Qt.QFrame.Plain)
            self.frame.setBackgroundRole(Qt.QPalette.Shadow)
            self.frame.setAutoFillBackground(True)
            self.frame.setSizePolicy(Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Fixed) # need for floating widgets too?
            self.title_label = Qt.QLabel()
            f = self.title_label.font()
            f.setBold(True)
            self.title_label.setAlignment(Qt.Qt.AlignLeft | Qt.Qt.AlignVCenter)
            self.title_label.setFont(f)
            l.addWidget(self.frame)
            ll = Qt.QVBoxLayout()
            ll.setContentsMargins(1,1,1,1)
            self.frame.setLayout(ll)
            ll.addWidget(self.title_label)
            ll.addSpacerItem(Qt.QSpacerItem(0, 0, Qt.QSizePolicy.Expanding))
            ll.addWidget(self.pop_button)
            l.addWidget(contained_widget)
        else:
            l.addWidget(contained_widget)
        self.visibility_change_action = Qt.QAction(contained_widget.windowTitle(), self)
        self.visibility_change_action.setCheckable(True)
        self.visibility_change_action.setChecked(False)
        self.visibility_change_action.toggled.connect(self.setVisible)
        contained_widget.windowTitleChanged.connect(self.on_contained_widget_window_title_changed)
        self.on_contained_widget_window_title_changed(contained_widget.windowTitle())

    def on_contained_widget_window_title_changed(self, t):
        self.visibility_change_action.setText(t)
        self.setWindowTitle(t)
        if hasattr(self, 'title_label'):
            self.title_label.setText("<font color='white'>{}</font>".format(t))

    def closeEvent(self, e):
        super().closeEvent(e)
        if e.isAccepted():
            self.visibility_change_action.setChecked(False)

    def showEvent(self, e):
        super().showEvent(e)
        if e.isAccepted():
            self.visibility_change_action.setChecked(True)

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