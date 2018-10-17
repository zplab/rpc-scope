# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt

class WidgetWindow(Qt.QMainWindow):
    def __init__(self, scope, widgets, window_title='Scope Widgets', parent=None):
        """Arguments:
            scope: instance of scope.scope_client.ScopeClient.
            widgets: list of widget information dictionaries as defined in build_gui
            parent: defaults to None, which is what you want if WidgetWindow is a top level window."""
        super().__init__(parent)
        self.setWindowTitle(window_title)
        self.central_widget = Qt.QWidget()
        self.central_widget.setLayout(FlowLayout(vSpacing=0))
        self.setCentralWidget(self.central_widget)
        self.visibility_toolbar = self.addToolBar('Visibility')

        self.action_toolbar = None
        self.action_widgets = []
        self.containers = []
        self.settings = Qt.QSettings('zplab', 'scope_widgets')
        geometry = self.settings.value('main_geometry')
        if geometry is not None:
            self.restoreGeometry(geometry)

        for widget_info in widgets:
            widget_class = widget_info['cls']
            if widget_class.can_run(scope):
                widget = widget_class(scope=scope)
                if isinstance(widget, Qt.QAction):
                    if self.action_toolbar is None:
                        self.action_toolbar = self.addToolBar('Actions')
                    self.action_toolbar.addAction(widget)
                    self.action_widgets.append(widget) # need to keep a reference arount, otherwise it goes away
                else:
                    self.add_widget(widget, widget_info['name'], widget_info.get('docked', False),
                        widget_info.get('start_visible', False), widget_info.get('pad', False))
        self.show()
        scope.rebroadcast_properties()

    def add_widget(self, widget, name, docked, visible, pad):
        container = HideableWidgetContainer(widget, name, docked, pad)
        container.setVisible(visible)
        self.containers.append(container)
        if docked:
            self.central_widget.layout().addWidget(container)

        else:
            container.setParent(None)
            geometry = self.settings.value(name + '_geometry')
            if geometry is not None:
                container.restoreGeometry(geometry)
        self.visibility_toolbar.addAction(container.visibility_change_action)

    def closeEvent(self, e):
        self.settings.setValue('main_geometry', self.saveGeometry())
        for container in self.containers:
            if not container.docked:
                self.settings.setValue(container.name + '_geometry', container.saveGeometry())
                container.close()
                container.contained_widget.close()
        super().closeEvent(e)


class HideableWidgetContainer(Qt.QWidget):
    def __init__(self, contained_widget, name, docked, pad):
        super().__init__()
        if name == 'viewer':
        self.contained_widget = contained_widget
        self.name = name
        layout = Qt.QVBoxLayout()
        self.setLayout(layout)
        self.docked = docked
        if docked:
            layout.setContentsMargins(-1, 0, -1, 6)
            layout.setSpacing(5)
            self.title_label = Qt.QLabel()
            f = self.title_label.font()
            f.setBold(True)
            self.title_label.setAlignment(Qt.Qt.AlignLeft | Qt.Qt.AlignVCenter)
            self.title_label.setFont(f)
            self.title_label.setBackgroundRole(Qt.QPalette.Shadow)
            self.title_label.setAutoFillBackground(True)
            layout.addWidget(self.title_label)
        else:
            if not pad:
                layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
        layout.addWidget(contained_widget)
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
            return v

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
