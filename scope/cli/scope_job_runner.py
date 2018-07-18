# This code is licensed under the MIT License (see LICENSE file for details)

import argparse
import time
import traceback
import sys

from .. import scope_job_runner

def parse_delay(arg):
    vals = arg.split(':')
    seconds = 0
    multipliers = [60*60, 60, 1] # seconds per hour and minute
    for val, multiplier in zip(vals, multipliers):
        try:
            val = int(val)
        except:
            raise argparse.ArgumentTypeError('Could not interpret {} as a time delay in h, h:m, or h:m:s format.'.format(arg))
        seconds += val * multiplier
    return time.time() + seconds

def main(argv=None):
    parser = argparse.ArgumentParser(description='microscope job control')
    parser.add_argument('-d', '--debug', action='store_true', help='show full stack traces on error')
    subparsers = parser.add_subparsers(help='sub-command help', dest='command')
    subparsers.required = True

    parser_start = subparsers.add_parser('start', help='start the job runner, if not running')
    parser_start.add_argument('-v', '--verbose', action='store_true', help='log extra debug information')

    parser_stop = subparsers.add_parser('stop', help='stop the job runner, if running')
    parser_stop.add_argument('-f', '--force', action='store_true', help='do not allow in-progress jobs to complete before stopping the runner')

    parser_status = subparsers.add_parser('status', help='print the status of the queued jobs')

    parser_add = subparsers.add_parser('add', help='add a new job to the queue')
    parser_add.set_defaults(func='add_job')
    parser_add.add_argument(metavar='py_file', dest='exec_file', help='python script to run')
    parser_add.add_argument(metavar='email', nargs='*', dest='alert_emails', help='email addresses to notify in case of error')
    parser_add.add_argument('-d', '--delay', metavar='DELAY', type=parse_delay, dest='next_run_time',
        help='time to delay before running the job (h, h:m, or h:m:s). Default: run immediately.',
        default='0')

    parser_remove = subparsers.add_parser('remove',
        help='remove a job from the queue (will not terminate the current job if running)')
    parser_remove.set_defaults(func='remove_job')
    parser_remove.add_argument(metavar='py_file', dest='exec_file', help='python script to remove')

    parser_resume = subparsers.add_parser('resume', help='resume a job previously suspended because of an error')
    parser_resume.set_defaults(func='resume_job')
    parser_resume.add_argument(metavar='py_file', dest='exec_file', help='python script to resume')
    parser_resume.add_argument('-d', '--delay', metavar='DELAY', type=parse_delay, dest='next_run_time',
        help='time to delay before next running the job (h, h:m, or h:m:s). If not specified, use the currently scheduled next-run time')

    parser_resume_all = subparsers.add_parser('resume_all', help='resume all jobs suspended because of an error')

    parser_purge = subparsers.add_parser('purge', help='purge jobs that are queued but have no future runs scheduled')

    parser_duty = subparsers.add_parser('duty', help='print the recent duty cycle (i.e. %% utilization)')
    parser_duty.set_defaults(func='duty_cycle')

    args = parser.parse_args(argv)

    try:
        runner = scope_job_runner.JobRunner()
        if args.command == 'start':
            runner.start(args.verbose)
        elif args.command == 'stop':
            if args.force:
                runner.terminate()
            else:
                runner.stop()
        else:
            arg_dict = dict(vars(args))
            del arg_dict['debug']
            if 'func' in arg_dict:
                func_name = arg_dict.pop('func')
                del arg_dict['command']
            else:
                func_name = arg_dict.pop('command')
            func = getattr(runner, func_name)
            func(**arg_dict)
    except Exception as e:
        if args.debug:
            traceback.print_exc(file=sys.stderr)
        else:
            sys.stderr.write(str(e)+'\n')
        return 1

if __name__ == '__main__':
    main()