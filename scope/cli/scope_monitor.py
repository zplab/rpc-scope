# This code is licensed under the MIT License (see LICENSE file for details)

import argparse

from ..gui import build_gui

def main(argv=None):
    parser = argparse.ArgumentParser(description="remote microscope monitor")
    parser.add_argument('hosts', nargs="+", metavar='HOST', help='the hosts to monitor')
    parser.add_argument('--downsample', default=3, type=int, help='image downsampling to reduce load (default %(default)s).')
    parser.add_argument('--fps-max', type=int, default=5, help='maximum image update FPS to reduce load')
    args = parser.parse_args(argv)
    build_gui.monitor_main(args.hosts, args.downsample, args.fps_max)

if __name__ == '__main__':
    main()