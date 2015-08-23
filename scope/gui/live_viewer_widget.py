from PyQt5 import Qt

from ris_widget import om, ris_widget
from .. import scope_client

class LiveViewerWidget(ris_widget.RisWidget):
    RW_LIVE_STREAM_BINDING_LIVE_UPDATE_EVENT = 1001

    @staticmethod
    def can_run(scope):
        return hasattr(scope, 'camera')

    def __init__(
            self,
            scope, scope_properties,
            window_title='RisWidget', parent=None, window_flags=Qt.Qt.WindowFlags(0), msaa_sample_count=2,
            **kw):
        super().__init__(
            window_title=window_title, parent=parent, window_flags=window_flags, msaa_sample_count=msaa_sample_count,
            **kw)
        self.scope = scope
        self.dupe_up_action = Qt.QAction('Dupe Up', self)
        self.dupe_up_action.triggered.connect(self.dupe_up)
        self.live_viewer_toolbar = self.addToolBar('Live')
        self.live_viewer_toolbar.addAction(self.dupe_up_action)
        self.live_streamer = scope_client.LiveStreamer(scope, scope_properties, self.post_live_update)
        self.pos_table_widget = PosTableWidget()
        self.pos_table_dock_widget = Qt.QDockWidget('Positions', self)
        self.pos_table_dock_widget.setWidget(self.pos_table_widget)
        self.pos_table_dock_widget.setAllowedAreas(Qt.Qt.AllDockWidgetAreas)
        self.pos_table_dock_widget.setFeatures(Qt.QDockWidget.DockWidgetClosable | Qt.QDockWidget.DockWidgetFloatable | Qt.QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.Qt.RightDockWidgetArea, self.pos_table_dock_widget)
        self.live_viewer_toolbar.addAction(self.pos_table_dock_widget.toggleViewAction())
        self.pos_table_dock_widget.hide()
        self.store_current_pos_action = Qt.QAction(self)
        self.store_current_pos_action.setText('Store Current Position')
        self.store_current_pos_action.setToolTip('shortcut: p')
        self.store_current_pos_action.setShortcut(Qt.Qt.Key_P)
        self.store_current_pos_action.setShortcutContext(Qt.Qt.ApplicationShortcut)
        self.store_current_pos_action.triggered.connect(self.store_current_pos)
        self.live_viewer_toolbar.addAction(self.store_current_pos_action)

    def event(self, e):
        # This is called by the main QT event loop to service the event posted in post_live_update().
        if e.type() == self.RW_LIVE_STREAM_BINDING_LIVE_UPDATE_EVENT:
            image_data, frame_no = self.live_streamer.get_image()
            self.image = self.ImageClass(image_data, is_twelve_bit=self.live_streamer.bit_depth=='12 Bit')
            return True
        return super().event(e)

    def post_live_update(self):
        # posting an event does not require calling thread to have an event loop,
        # unlike sending a signal
        Qt.QCoreApplication.postEvent(self, Qt.QEvent(self.RW_LIVE_STREAM_BINDING_LIVE_UPDATE_EVENT))

    def dupe_up(self):
        """If self.bottom_layer and self.bottom_layer.image are not None, duplicate self.bottom_layer.image,
        wrap it in a Layer, and insert that layer into self.image_stack at index 1."""
        bottom_layer = self.bottom_layer
        if bottom_layer is not None:
            bottom_image = bottom_layer.image
            if bottom_image is not None:
                dupe_image = self.ImageClass(bottom_image.data, is_twelve_bit=bottom_image.is_twelve_bit)
                self.layer_stack.insert(1, self.LayerClass(dupe_image))

    def store_current_pos(self):
        if not self.pos_table_dock_widget.isVisible():
            self.pos_table_dock_widget.show()
        self.positions_signaling_list.append(Pos(*self.scope.stage.position))

    @property
    def positions_signaling_list(self):
        return self.pos_table_widget.model.signaling_list

    @positions_signaling_list.setter
    def positions_signaling_list(self, v):
        self.pos_table_widget.model.signaling_list = v

    @property
    def positions(self):
        return [(e.x, e.y, e.z) for e in self.positions_signaling_list]

    @positions.setter
    def positions(self, v):
        self.positions_signaling_list = om.SignalingList(Pos(*e) for e in v)

class PosTableWidget(Qt.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = PosTableModel(('x', 'y', 'z'), om.SignalingList(), self)
        self.view = PosTableView(self.model, self)
        self.setLayout(Qt.QVBoxLayout())
        self.layout().addWidget(self.view)

class PosTableView(Qt.QTableView):
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.horizontalHeader().setSectionResizeMode(Qt.QHeaderView.ResizeToContents)
        self.setDragDropOverwriteMode(False)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(Qt.QAbstractItemView.InternalMove)
        self.setDropIndicatorShown(True)
        self.setSelectionBehavior(Qt.QAbstractItemView.SelectRows)
        self.setSelectionMode(Qt.QAbstractItemView.SingleSelection)
        self.delete_current_row_action = Qt.QAction(self)
        self.delete_current_row_action.setText('Delete current row')
        self.delete_current_row_action.triggered.connect(self._on_delete_current_row_action_triggered)
        self.delete_current_row_action.setShortcut(Qt.Qt.Key_Delete)
        self.delete_current_row_action.setShortcutContext(Qt.Qt.WidgetShortcut)
        self.addAction(self.delete_current_row_action)
        self.setModel(model)

    def _on_delete_current_row_action_triggered(self):
        sm = self.selectionModel()
        m = self.model()
        if None in (m, sm):
            return
        midx = sm.currentIndex()
        if midx.isValid():
            m.removeRow(midx.row())

class PosTableModel(om.signaling_list.DragDropModelBehavior, om.signaling_list.PropertyTableModel):
    pass

class Pos(Qt.QObject):
    changed = Qt.pyqtSignal(object)

    def __init__(self, x=None, y=None, z=None, parent=None):
        super().__init__(parent)
        for property in self.properties:
            property.instantiate(self)
        self.x, self.y, self.z = x, y, z

    properties = []

    def component_default_value_callback(self):
        pass

    def take_component_arg_callback(self, v):
        if v is not None:
            return float(v)

    x = om.Property(
        properties,
        "x",
        default_value_callback=component_default_value_callback,
        take_arg_callback=take_component_arg_callback)

    y = om.Property(
        properties,
        "y",
        default_value_callback=component_default_value_callback,
        take_arg_callback=take_component_arg_callback)

    z = om.Property(
        properties,
        "z",
        default_value_callback=component_default_value_callback,
        take_arg_callback=take_component_arg_callback)

    for property in properties:
        exec(property.changed_signal_name + ' = Qt.pyqtSignal(object)')
    del property
