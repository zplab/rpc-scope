# The MIT License (MIT)
#
# Copyright (c) 2014-2015 WUSTL ZPLAB
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
import ris_widget
import ris_widget.image
import ris_widget.layer
import ris_widget.ris_widget
import ris_widget.qwidgets.layer_table
from .. import scope_client

# TODO: Should live_target be a flipbook entry instead of a layer?
# If so, get rid of the layer-name showing.
# TODO: Fix vignette masking to use center and radius, and to have some
# UI for selecting same. Also, remove openmp stuff.

# Show layer name column in LayerTable
ris_widget.qwidgets.layer_table.LayerTableModel.PROPERTIES.insert(
    ris_widget.qwidgets.layer_table.LayerTableModel.PROPERTIES.index('opacity') + 1, 'name')

class ScopeViewerWidget(ris_widget.ris_widget.RisWidgetQtObject):
    NEW_IMAGE_EVENT = Qt.QEvent.registerEventType()
    OVEREXPOSURE_GETCOLOR_EXPRESSION = 's.r < 1.0f ? vec4(s.rrr, 1.0f) : vec4(1.0f, 0.0f, 0.0f, 1.0f)'

    @staticmethod
    def can_run(scope):
        return hasattr(scope, 'camera')

    def __init__(
            self,
            scope,
            scope_properties,
            window_title='Scope Viewer',
            parent=None,
            window_flags=Qt.Qt.WindowFlags(0),
            show=True,
            layers = tuple(),
            **kw):

        super().__init__(
            app_prefs_name=None,
            window_title=window_title,
            parent=parent,
            window_flags=window_flags,
            layers=layers,
            **kw)

        self.main_view_toolbar.removeAction(self.main_view_snapshot_action)
        self.dock_widget_visibility_toolbar.removeAction(self.layer_stack_painter_dock_widget.toggleViewAction())

        hh = self.layer_table_view.horizontalHeader()
        col = ris_widget.qwidgets.layer_table.LayerTableModel.PROPERTIES.index('name')
        hh.resizeSection(col, hh.sectionSize(col) * 1.5)
        self.scope_toolbar = self.addToolBar('Scope')
        self.live_streamer = scope_client.LiveStreamer(scope, scope_properties, self.post_new_image_event)
        import freeimage
        import pathlib
        if pathlib.Path('/home/zplab/vignette_mask.png').exists():
            self.layer_stack.imposed_image_mask = freeimage.read('/home/zplab/vignette_mask.png')
        self.show_over_exposed_action = Qt.QAction('Show Over-Exposed Live Pixels', self)
        self.show_over_exposed_action.setCheckable(True)
        self.show_over_exposed_action.setChecked(False)
        self.show_over_exposed_action.toggled.connect(self.on_show_over_exposed_action_toggled)
        self.show_over_exposed_action.setChecked(True)
        self.scope_toolbar.addAction(self.show_over_exposed_action)

    def event(self, e):
        # This is called by the main QT event loop to service the event posted in post_new_image_event().
        if e.type() == self.NEW_IMAGE_EVENT and self.isVisible() and self.live_streamer.image_ready():
            image_data, timestamp, frame_no = self.live_streamer.get_image()
            target_layer = self.get_live_target_layer()
            target_layer.image = ris_widget.image.Image(
                image_data,
                mask=self.layer_stack.imposed_image_mask,
                is_twelve_bit=self.live_streamer.bit_depth == '12 Bit',
                use_open_mp=True)
            if self.show_over_exposed_action.isChecked() and target_layer.image.type == 'G':
                target_layer.getcolor_expression = self.OVEREXPOSURE_GETCOLOR_EXPRESSION
            return True
        return super().event(e)

    def post_new_image_event(self):
        # posting an event does not require calling thread to have an event loop,
        # unlike sending a signal
        Qt.QCoreApplication.postEvent(self, Qt.QEvent(self.NEW_IMAGE_EVENT))

    def get_live_target_layer(self):
        """The first Layer in self.layers with name "Live Target" is returned.  If self.layers contains no Layer with name
        "Live Target", one is created, inserted at index 0, and returned."""
        if self.layers is None:
            self.layers = []
        else:
            for layer in self.layers:
                if layer.name == 'Live Target':
                    return layer
        t = ris_widget.layer.Layer(name='Live Target')
        self.layers.insert(0, t)
        return t

    def on_show_over_exposed_action_toggled(self, show_over_exposed):
        layer = self.get_live_target_layer()
        if show_over_exposed:
            if layer.image is not None and layer.image.type == 'G':
                layer.getcolor_expression = self.OVEREXPOSURE_GETCOLOR_EXPRESSION
        else:
            # Revert to default getcolor_expression
            del layer.getcolor_expression

