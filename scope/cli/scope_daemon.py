# TODO: UGLY HACK to get around the fact that importing pyfftw after numpy breaks things on some systems (WTF?)
import pyfftw
import argparse
import traceback

from ..util import json_encode
from .. import scope_server

def main(argv):
    parser = argparse.ArgumentParser(description='microscope server control')
    parser.add_argument('--debug', action='store_true', help='show full stack traces on error')
    subparsers = parser.add_subparsers(help='sub-command help', dest='command')
    subparsers.required = True
    parser_start = subparsers.add_parser('start', help='start the microscope server, if not running')
    parser_start.add_argument('--public', action='store_true', help='Allow network connections to the server [default: allow only local connections]')
    parser_start.add_argument('--verbose', action='store_true', help='Log all RPC calls and property state changes.')
    parser_stop = subparsers.add_parser('stop', help='stop the microscope server, if running')
    parser_stop.add_argument('-f', '--force', action='store_true', help='forcibly kill the server process')
    parser_restart = subparsers.add_parser('restart', help='restart the microscope server, if running')
    parser_restart.add_argument('-f', '--force', action='store_true', help='forcibly kill the server process')
    parser_status = subparsers.add_parser('status', help='report whether the microscope server is running')
    args = parser.parse_args(argv)

    try:
        server = scope_server.ScopeServer()
        if args.command == 'status':
            server.status()
        if args.command in {'stop', 'restart'}:
            server.stop(args.force)
        if args.command == 'start':
            with server.arg_file.open('w') as f:
                json_encode.encode_legible_to_file(dict(public=args.public, verbose=args.verbose), f)
        if args.command in {'start', 'restart'}:
            server.start()
    except Exception as e:
        if args.debug:
            traceback.print_exc(file=sys.stderr)
        else:
            sys.stderr.write(str(e)+'\n')
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:]))
