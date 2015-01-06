import argparse

from ..gui import andor_camera_widget
from ..gui import lamp_widget
from ..gui import live_viewer_widget
from ..gui import build_gui

WIDGETS = {
    'camera': andor_camera_widget.AndorCameraWidget,
    'lamps': lamp_widget.LampWidget,
    'viewer': live_viewer_widget.LiveViewerWidget
}

def main(argv):
    parser = argparse.ArgumentParser(description="microscope GUI")
    parser.add_argument('widgets', nargs="*", choices=['camera', 'viewer', 'lamps', 'all'], default='all',
            help='the widget(s) to show %(prog)s (default: %(default)s)')
    args = parser.parse_args()
    widgets = [WIDGETS[name] for name in set(args.widgets)]
    build_gui.gui_main(widgets)

if __name__ == '__main__':
    import sys
    main(sys.argv)
