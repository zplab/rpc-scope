from PyQt5 import Qt

from ris_widget import ris_widget
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
        self.dupe_up_action = Qt.QAction('Dupe Up', self)
        self.dupe_up_action.triggered.connect(self.dupe_up)
        self.live_viewer_toolbar = self.addToolBar('Live')
        self.live_viewer_toolbar.addAction(self.dupe_up_action)
        self.live_streamer = scope_client.LiveStreamer(scope, scope_properties, self.post_live_update)

    def event(self, e):
        # This is called by the main QT event loop to service the event posted in post_live_update().
        if e.type() == self.RW_LIVE_STREAM_BINDING_LIVE_UPDATE_EVENT:
            image, frame_no = self.live_streamer.get_image()
            if self.bottom_layer is None:
                self.bottom_layer = self.LayerClass()
            self.bottom_layer.image = self.ImageClass(image, is_twelve_bit=self.live_streamer.scope.camera.bit_depth=='12 Bit')
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
