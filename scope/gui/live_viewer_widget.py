from PyQt5 import Qt

from ris_widget import ris_widget
from ris_widget.image import image as ris_widget_image
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
        self.dupe_down_action = Qt.QAction('Dupe Down', self)
        self.dupe_down_action.triggered.connect(self.dupe_down)
        self.live_viewer_toolbar = self.addToolBar('Live')
        self.live_viewer_toolbar.addAction(self.dupe_down_action)
        self.live_streamer = scope_client.LiveStreamer(scope, scope_properties, self.post_live_update)

    def event(self, e):
        # This is called by the main QT event loop to service the event posted in post_live_update().
        if e.type() == self.RW_LIVE_STREAM_BINDING_LIVE_UPDATE_EVENT:
            image, frame_no = self.live_streamer.get_image()
            if not self.image:
                rwimage = ris_widget_image.Image(image, is_twelve_bit=self.live_streamer.scope.camera.bit_depth=='12 Bit')
                self.image = rwimage
            else:
                self.image.set_data(image, is_twelve_bit=self.live_streamer.scope.camera.bit_depth=='12 Bit')
            return True
        return super().event(e)

    def post_live_update(self):
        # posting an event does not require calling thread to have an event loop,
        # unlike sending a signal
        Qt.QCoreApplication.postEvent(self, Qt.QEvent(self.RW_LIVE_STREAM_BINDING_LIVE_UPDATE_EVENT))

    def dupe_down(self):
        """If self.image (ie, self.image_stack[0]) is not None, duplicate it and insert the copy
        as self.image_stack[1]."""
        orig = self.image
        if orig is not None:
            dupe = ris_widget_image.Image(orig.data, is_twelve_bit=orig.is_twelve_bit)
            dupe.copy_property_values_from(orig)
            self.image_stack.insert(1, dupe)
