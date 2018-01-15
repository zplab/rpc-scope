# -*- coding: utf-8 -*-
# This code is licensed under the MIT License (see LICENSE file for details)

import platform
import datetime
import sys
import pathlib
import subprocess

from .. import scope_job_runner
from ..config import scope_configuration

ERROR_SUBJECT = '{host}: scope jobs are queued but scope_job_runner is inactive.'
ERROR_MESSAGE = '''One or more of your jobs is queued on {host}, but the scope job runner daemon is not running.
These jobs will not be run until the command `scope_job_runner start` is executed on that machine.

Time: {time}
Queued Jobs:
{jobs}
'''

def main(scope_host='127.0.0.1'):
    if len(sys.argv) == 2 and sys.argv[1] == '--install':
        return install_systemd_units(sys.argv[0])

    runner = scope_job_runner.JobRunner()
    problem_file = scope_configuration.CONFIG_DIR / '.jobs_queued_but_runner_inactive'
    if runner.is_running():
        if problem_file.exists():
            # job runner was restarted; problem is cleared. Remove the problem-file flag
            problem_file.unlink()
        return

    # job runner is not running. Check if there are queued jobs with people to alert
    exec_dir = pathlib.Path(sys.argv[0]).parent
    queued_jobs = []
    to_email = set()
    for job in runner.jobs.get_jobs():
        if job.exec_file.parent == exec_dir:
            # Not a user-provided job. Instead is something like incubator_check
            continue
        if job.status == scope_job_runner.STATUS_QUEUED and job.next_run_time is not None and job.alert_emails:
            to_email.update(job.alert_emails)
            queued_jobs.append(job)

    if not queued_jobs: # no jobs running that anyone cares about
        return

    print('Jobs queued but job runner is not running.')

    if problem_file.exists():
        # this error was previously detected
        previously_emailed = set(problem_file.read_text().split('\n'))
    else:
        previously_emailed = set()
    to_email -= previously_emailed

    if to_email:
        # we have not alerted some people about the queued jobs
        host = platform.node().split('.')[0]
        now = datetime.datetime.now().replace(microsecond=0).isoformat(' ')
        job_blurbs = '\n'.join(runner.format_job_blurb(job) for job in queued_jobs)
        message = ERROR_MESSAGE.format(host=host, time=now, jobs=job_blurbs)
        print('Emailing alert about the following jobs:\n{}'.format(job_blurbs))
        subject = ERROR_SUBJECT.format(host=host)
        runner.send_error_email(sorted(to_email), subject, message)
        problem_file.write_text('\n'.join(to_email | previously_emailed))
    else:
        print('No alert emailed: all relevant parties have already been emailed.')


TIMER_UNIT = '''[Unit]
Description=Check that scope_job_runner is active if jobs are queued

[Timer]
OnBootSec=15min
OnActiveSec=30min

[Install]
WantedBy=timers.target
'''

SERVICE_UNIT = '''[Unit]
Description=Check that scope_job_runner is active if jobs are queued

[Service]
ExecStart={executable}
'''

def install_systemd_units(executable):
    base_unit = pathlib.Path('/etc/systemd/system/job_runner_check')
    timer_file = base_unit.with_suffix('.timer')
    timer_file.write_text(TIMER_UNIT)
    timer_file.chmod(0o644)
    service_file = base_unit.with_suffix('.service')
    service_file.write_text(SERVICE_UNIT.format(executable=executable))
    service_file.chmod(0o644)
    subprocess.run(['systemctl', 'enable', base_unit.name], check=True)
    subprocess.run(['systemctl', 'start', base_unit.name], check=True)
    subprocess.run(['systemctl', 'status', base_unit.name], check=True)


