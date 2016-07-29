import argparse

from ..gui import build_gui
from ..gui import scope_widgets

def main(argv):
    parser = argparse.ArgumentParser(description="microscope GUI")
    choices = sorted(scope_widgets.WIDGETS.keys())
    choices.append('all')
    parser.add_argument(
        'widgets', nargs="*", choices=choices, default='all',
        help='the widget(s) to show %(prog)s (default: %(default)s)')
    parser.add_argument('--host', default='127.0.0.1', help='microscope host to connect to (default %(default)s')
    args = parser.parse_args(argv)
    if not isinstance(args.widgets, list):
        args.widgets = [args.widgets]
    build_gui.gui_main(args.host, set(args.widgets))

if __name__ == '__main__':
    import sys
    main(sys.argv[1:])