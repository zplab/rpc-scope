import argparse
import os.path
import sys
import time
import traceback

from ..timecourse import scope_job_runner

def make_runner(base_dir='~'):
    base_dir = os.path.realpath(os.path.expanduser(base_dir))
    backingfile_path = os.path.join(base_dir, 'scope_jobs.json')
    jobfile_path = os.path.join(base_dir, 'scope_job_current')
    pidfile_path = os.path.join(base_dir, 'scope_job_runner.pid')
    log_dir = os.path.join(base_dir, 'scope_job_logs')
    runner = scope_job_runner.JobRunner(backingfile_path, jobfile_path, pidfile_path)
    return runner, log_dir

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

def main(argv):
    # scope_job_daemon [start --verbose | stop | add_job exec_file email ]

    parser = argparse.ArgumentParser(description='microscope job control')
    parser.add_argument('-d', '--debug', action='store_true', help='show full stack traces on error')
    subparsers = parser.add_subparsers(help='sub-command help', dest='command')
    subparsers.required = True
    parser_start = subparsers.add_parser('start', help='start the job runner, if not running')
    parser_start.add_argument('-v', '--verbose', action='store_true', help='log extra debug information')
    parser_stop = subparsers.add_parser('stop', help='stop the job runner, if running')
    parser_stop.add_argument('-f', '--force', action='store_true', help='do not allow in-progress jobs to complete before stopping the runner')
    parser_status = subparsers.add_parser('status', help='print the status of the queued jobs')
    parser_status.set_defaults(func='status')
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
    parser_suspend = subparsers.add_parser('suspend',
        help='suspend a job (do not remove from queue, but do not run again until it is resumed)')
    parser_suspend.set_defaults(func='suspend_job')
    parser_suspend.add_argument(metavar='py_file', dest='exec_file', help='python script to suspend')
    parser_resume = subparsers.add_parser('resume', help='resume a job previously suspended manually or because of an error')
    parser_resume.set_defaults(func='resume_job')
    parser_resume.add_argument(metavar='py_file', dest='exec_file', help='python script to resume')
    parser_resume.add_argument('-d', '--delay', metavar='DELAY', type=parse_delay, dest='next_run_time',
        help='time to delay before next running the job (h, h:m, or h:m:s). If not specified, use the currently scheduled next-run time')

    args = parser.parse_args()

    try:
        runner, log_dir = make_runner()
        if args.command == 'start':
            runner.start(log_dir, args.verbose)
        elif args.command == 'stop':
            if args.force:
                runner.terminate()
            else:
                runner.stop()
        else args.command:
            arg_dict = dict(vars(args))
            del arg_dict['command']
            del arg_dict['debug']
            func = getattr(runner, arg_dict.pop('func'))
            func(**arg_dict)
    except Exception as e:
        if args.debug:
            traceback.print_exc(file=sys.stderr)
        else:
            sys.stderr.write(str(e)+'\n')
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv))
