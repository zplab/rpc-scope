import argparse

from ..gui import build_gui

def main(argv):
    parser = argparse.ArgumentParser(description="microscope GUI")
    parser.add_argument('widgets', nargs="*", choices=['camera', 'viewer', 'lamps', 'microscope', 'all'], default='all',
            help='the widget(s) to show %(prog)s (default: %(default)s)')
    parser.add_argument('--host', default='127.0.0.1', help='microscope host to connect to (default %(default)s')
    args = parser.parse_args(argv)
    if not isinstance(args.widgets, list):
        args.widgets = [args.widgets]
    build_gui.gui_main(args.host, set(args.widgets))

if __name__ == '__main__':
    import sys
    main(sys.argv[1:])