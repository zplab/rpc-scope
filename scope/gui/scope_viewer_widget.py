# This code is licensed under the MIT License (see LICENSE file for details)

import time
import datetime

from PyQt5 import Qt
from  ris_widget import image
from ris_widget import ris_widget
import freeimage

from .. import scope_client

# TODO: Should live_target be a flipbook entry instead of just self.image?

class ScopeViewerWidget(ris_widget.RisWidgetQtObject):
    NEW_IMAGE_EVENT = Qt.QEvent.registerEventType()
    OVEREXPOSURE_GETCOLOR_EXPRESSION = 's.r < 1.0f ? vec4(s.rrr, 1.0f) : vec4(1.0f, 0.0f, 0.0f, 1.0f)'

    @staticmethod
    def can_run(scope):
        return hasattr(scope, 'camera')

    def __init__(self, scope, scope_properties, window_title='Viewer', fps_max=None, app_prefs_name='scope-viewer', parent=None):
        super().__init__(window_title=window_title, app_prefs_name=app_prefs_name, parent=parent)
        self.main_view_toolbar.removeAction(self.snapshot_action)

        self.scope_toolbar = self.addToolBar('Scope')
        self.show_over_exposed_action = Qt.QAction('Show Over-Exposed', self)
        self.show_over_exposed_action.setCheckable(True)
        self.show_over_exposed_action.setChecked(True)
        self.show_over_exposed_action.toggled.connect(self.on_show_over_exposed_action_toggled)
        self.scope_toolbar.addAction(self.show_over_exposed_action)

        self.flipbook.pages.append(image.Image([[0]], name='Live Image'))
        self.flipbook.hide()
        self.image = None

        self.camera = scope.camera
        self.snap_action = Qt.QAction('Snap Image', self)
        self.snap_action.triggered.connect(self.snap_image)
        self.scope_toolbar.addAction(self.snap_action)

        self.save_action = Qt.QAction('Save Image', self)
        self.save_action.triggered.connect(self.save_image)
        self.scope_toolbar.addAction(self.save_action)

        self.closing = False
        self.live_streamer = scope_client.LiveStreamer(scope, scope_properties, self.post_new_image_event)
        if fps_max is None:
            self.interval_min = None
        else:
            self.interval_min = 1/fps_max
        self.last_image = 0

    def closeEvent(self, e):
        if self.closing:
            # sometimes closeEvent gets fired off twice (2018-01, PyQt 5.9). Why? TODO: verify if problem goes away in later Qt
            return
        self.closing = True
        self.live_streamer.detach()
        super().closeEvent(e)

    def event(self, e):
        # This is called by the main QT event loop to service the event posted in post_new_image_event().
        if e.type() == self.NEW_IMAGE_EVENT and self.live_streamer.image_ready():
            if self.interval_min is not None:
                t = time.time()
                if t - self.last_image < self.interval_min:
                    return True
                self.last_image = t
            self.flipbook.current_page_idx = 0
            image_data, timestamp, frame_no = self.live_streamer.get_image()
            image_bits = 12 if self.live_streamer.bit_depth == '12 Bit' else 16
            self.image = image.Image(image_data, image_bits=image_bits)
            if self.show_over_exposed_action.isChecked() and self.layer.image.type == 'G':
                self.layer.getcolor_expression = self.OVEREXPOSURE_GETCOLOR_EXPRESSION
            else:
                del self.layer.getcolor_expression
            return True
        return super().event(e)

    def post_new_image_event(self):
        # posting an event does not require calling thread to have an event loop,
        # unlike sending a signal
        if not self.closing and self.isVisible():
            Qt.QCoreApplication.postEvent(self, Qt.QEvent(self.NEW_IMAGE_EVENT))

    def on_show_over_exposed_action_toggled(self, show_over_exposed):
        if show_over_exposed:
            if self.layer.image is not None and self.layer.image.type == 'G':
                self.layer.getcolor_expression = self.OVEREXPOSURE_GETCOLOR_EXPRESSION
        else:
            # Revert to default getcolor_expression
            del self.layer.getcolor_expression

    def snap_image(self):
        self.flipbook.pages.append_named(self.camera.acquire_image(), datetime.datetime.now().isoformat(' ', 'seconds'))

    def save_image(self):
        fn, _ = Qt.QFileDialog.getSaveFileName(self, 'Save Image', filter='Images (*.png *.tiff *.tif)')
        if fn:
            freeimage.write(self.image.data, fn)
