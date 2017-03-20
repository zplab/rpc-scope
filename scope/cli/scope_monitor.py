import argparse

from ..gui import build_gui

def main(argv=None):
    parser = argparse.ArgumentParser(description="remote microscope monitor")
    choices = ', '.join(sorted(build_gui.WIDGET_NAMES))
    parser.add_argument('hosts', nargs="+", metavar='HOST', help='the hosts to monitor')
    parser.add_argument('--downsample', default=3, type=int, help='image downsampling to reduce compression and network load (default %(default)s).')
    args = parser.parse_args(argv)
    build_gui.monitor_main(args.hosts, args.downsample)
