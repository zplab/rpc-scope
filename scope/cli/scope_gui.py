# This code is licensed under the MIT License (see LICENSE file for details)

import argparse

from ..gui import build_gui

def main(argv=None):
    parser = argparse.ArgumentParser(description="microscope GUI")
    parser.add_argument('host', nargs='?', default='127.0.0.1', help='microscope host to connect to (default %(default)s)')
    args = parser.parse_args(argv)
    build_gui.gui_main(args.host)

if __name__ == '__main__':
    main()