import argparse

from ..gui import andor_camera_widget
from ..gui import lamp_widget
from ..gui import live_viewer_widget
from ..gui import microscope_widget
from ..gui import build_gui

WIDGETS = {
    'camera': andor_camera_widget.AndorCameraWidget,
    'lamps': lamp_widget.LampWidget,
    'viewer': live_viewer_widget.LiveViewerWidget,
    'microscope': microscope_widget.MicroscopeWidget
}

def main(argv):
    parser = argparse.ArgumentParser(description="microscope GUI")
    parser.add_argument('widgets', nargs="*", choices=['camera', 'viewer', 'lamps', 'microscope', 'all'], default='all',
            help='the widget(s) to show %(prog)s (default: %(default)s)')
    parser.add_argument('--host', default='127.0.0.1', help='microscope host to connect to (default %(default)s')
    args = parser.parse_args(argv)
    if not isinstance(args.widgets, list):
        args.widgets = [args.widgets]
    widgets = set(args.widgets)
    if 'all' in widgets:
        widgets = WIDGETS
    else:
        widgets = {name: WIDGETS[name] for name in widgets}
    
    build_gui.gui_main(args.host, **widgets)

if __name__ == '__main__':
    import sys
    main(sys.argv[1:])
