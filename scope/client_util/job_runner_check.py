# -*- coding: utf-8 -*-
# This code is licensed under the MIT License (see LICENSE file for details)

import platform
import datetime
import sys
import pathlib
import subprocess
import time

from .. import scope_job_runner
from ..config import scope_configuration

def main():
    if len(sys.argv) == 2 and sys.argv[1] == '--install':
        install_systemd_units()
    else:
        check_job_runner()

TIMER_UNIT = '''[Unit]
Description=Check that scope_job_runner is active if jobs are queued

[Timer]
OnBootSec=15min
OnActiveSec=45min

[Install]
WantedBy=timers.target
'''

SERVICE_UNIT = '''[Unit]
Description=Check that scope_job_runner is active if jobs are queued

[Service]
ExecStart={executable}
'''

def install_systemd_units():
    base_unit = pathlib.Path('/etc/systemd/system/job_runner_check')
    timer_file = base_unit.with_suffix('.timer')
    timer_file.write_text(TIMER_UNIT)
    timer_file.chmod(0o644)
    service_file = base_unit.with_suffix('.service')
    service_file.write_text(SERVICE_UNIT.format(executable=sys.argv[0]))
    service_file.chmod(0o644)
    subprocess.run(['systemctl', 'enable', timer_file.name], check=True)
    subprocess.run(['systemctl', 'start', timer_file.name], check=True)
    print(f'systemd units installed. Run systemctl status {timer_file.name} or {base_unit.name} to check.')


ERROR_SUBJECT = '{host}: scope job pending but scope_job_runner is inactive.'
ERROR_MESSAGE = '''One or more of your jobs is overdue on {host}, but the scope job runner daemon is not running.
These jobs will not be run until the command `scope_job_runner start` is executed on that machine.

Time: {time}
Queued Jobs:
{jobs}
'''

ALL_CLEAR_SUBJECT = '{host}: scope_job_runner was reactivated.'
ALL_CLEAR_MESSAGE = '''One or more of your jobs on {host} was stalled due to an inactive job runner.
The job runner has now been restarted and your jobs will be run as planned.

Time: {time}
Queued Jobs:
{jobs}
'''

def check_job_runner():
    runner = scope_job_runner.JobRunner()
    problem_file = scope_configuration.CONFIG_DIR / '.jobs_queued_but_runner_inactive'
    overdue_jobs, to_email = get_overdue_jobs(runner)
    if len(overdue_jobs) == 0:
        return

    if runner.is_running():
        if problem_file.exists():
            # job runner was restarted; problem is cleared.
            # Alert previous email recipients that things are good now
            print('Previous error, but now job runner is running.')
            send_email(to_email, runner, overdue_jobs, ALL_CLEAR_SUBJECT, ALL_CLEAR_MESSAGE, 'all-clear')
            # Remove the problem-file flag
            problem_file.unlink()
    else: # job runner is not running.
        print('Jobs queued but job runner is not running.')
        previously_emailed = set()
        if problem_file.exists():
            # this error was previously detected
            previously_emailed.update(problem_file.read_text().split('\n'))
        to_email -= previously_emailed
        if to_email:
            # we have not alerted some people about the queued jobs
            send_email(to_email, runner, overdue_jobs, ERROR_SUBJECT, ERROR_MESSAGE, 'alert')
            problem_file.write_text('\n'.join(to_email | previously_emailed))
        else:
            print('No alert emailed: all relevant parties have already been emailed.')

def get_overdue_jobs(runner):
    # Get overdue jobs that anyone cares about (e.g. that aren't system checks and have
    # emails attached).
    now = time.time()
    exec_dir = pathlib.Path(sys.argv[0]).parent
    overdue_jobs = []
    to_email = set()
    for job in runner.jobs.get_jobs():
        if ( job.exec_file.parent == exec_dir and # job is user-provided, not like incubator_check
             job.status == scope_job_runner.STATUS_QUEUED and # and is active
             job.next_run_time is not None and # and is scheduled to run again
             job.next_run_time < now and # and is overdue
             job.alert_emails ): # and has a non-empty, non-None list of people to alert
            overdue_jobs.append(job)
            to_email.update(job.alert_emails)
    return overdue_jobs, to_email

def send_email(to_email, runner, jobs, subject_template, body_template, email_type):
    host = platform.node().split('.')[0]
    now = datetime.datetime.now().isoformat(sep=' ', timespec='seconds')
    subject = subject_template.format(host=host)
    job_blurbs = '\n'.join(runner.format_job_blurb(job) for job in jobs)
    message = body_template.format(host=host, time=now, jobs=job_blurbs)
    print('Emailing {} about the following jobs:\n{}'.format(email_type, job_blurbs))
    runner.send_error_email(sorted(to_email), subject, message)
