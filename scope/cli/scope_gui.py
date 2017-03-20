import argparse

from ..gui import build_gui

def main(argv=None):
    parser = argparse.ArgumentParser(description="microscope GUI")
    choices = ', '.join(sorted(build_gui.WIDGET_NAMES))
    parser.add_argument('widgets', nargs="*", metavar='WIDGET',
        help='the widget(s) to display, or all if none are specified (valid options: {})'.format(choices))
    parser.add_argument('--host', default='127.0.0.1', help='microscope host to connect to (default %(default)s')
    args = parser.parse_args(argv)
    if len(args.widgets) == 0:
        desired_widgets = None
    else:
        # uniquify requested widgets; widget-name validation is done in build_gui
        desired_widgets = set(args.widgets)
    build_gui.gui_main(args.host, desired_widgets)
