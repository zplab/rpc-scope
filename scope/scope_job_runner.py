# This code is licensed under the MIT License (see LICENSE file for details)

import sys
import time
import datetime
import subprocess
import pathlib
import os
import select
import signal
import json
import collections
import smtplib
import platform
import email.mime.text as mimetext

import lockfile
from zplib import datafile

from .config import scope_configuration
from .util import base_daemon
from .util import logging
logger = logging.get_logger(__name__)

STATUS_QUEUED = 'queued'
STATUS_ERROR = 'error'

HEARTBEAT_BYTES = b'\n'
HEARTBEAT_TIMEOUT = 5*60 # in seconds

def main(timepoint_function):
    """Example main function designed to interact with the job running daemon, which
    starts a process with the timestamp of the scheduled start time as the first
    argument, and expects stdout to contain the timestamp of the next scheduled
    run-time.

    Parameters:
        timepoint_function: function to call to do whatever the job is supposed
            to do during its invocation. Usually it will be the run_timepoint
            method of a TimepointHandler subclass. The function must return
            the number of seconds the job-runner should wait before running
            the job again. If None is returned, then the job will not be re-run.
            The scheduled starting timestamp will be passed to timepoint_function
            as a parameter.
    """
    if len(sys.argv) > 1:
        scheduled_start = float(sys.argv[1])
    else:
        scheduled_start = time.time()
    next_run_time = timepoint_function(scheduled_start)
    if next_run_time:
        print(next_run_time)

class JobRunner(base_daemon.Runner):
    def __init__(self):
        self.base_dir = scope_configuration.CONFIG_DIR
        self.jobs = _JobList(self.base_dir / 'jobs.json')
        self.current_job = _JobFile(self.base_dir / 'job_current')
        self.log_dir = self.base_dir / 'job_logs'
        self.audit_log = self.log_dir / 'audit_log'
        super().__init__(name='Scope Job Manager', pidfile_path=self.base_dir / 'scope_job_runner.pid')

    def _log_audit_message(self, message):
        isotime = datetime.datetime.now().isoformat('t', 'seconds')
        with self.audit_log.open('a') as log:
            log.write(f'{isotime}> {message}\n')

    # THE FOLLOWING FUNCTIONS ARE FOR COMMUNICATING WITH / STARTING A RUNNING DAEMON
    def add_job(self, exec_file, alert_emails, next_run_time='now'):
        """Add a job to the queue.

        Parameters:
            exec_file: path to python file to run. The requested run-time is passed
                to the exec_file as the first argument as a time.time() timestamp.
                (The requested run-time might not be the actual time the file is run
                if a previous job takes over-long.) The standard output from running
                this file, if present, will be interpreted as the timestamp to run
                the job again.
            alert_emails: one email address as a string, list/tuple of multiple emails, or None.
                If not None, then these email addresses will be alerted if the job fails.
            next_run_time: either a time.time() style timestamp, or 'now'.
            """
        job = self.jobs.add(exec_file, alert_emails, next_run_time, STATUS_QUEUED)
        self._log_audit_message(f'Added job: {job.exec_file}')
        if self.is_running():
            self._awaken_daemon()
        else:
            print('NOTE: The job-runner is NOT CURRENTLY RUNNING. Until it is started again, this job WILL NOT BE RUN.')

    def remove_job(self, exec_file):
        """Remove the job specified by the given exec_file.

        Note: this will NOT terminate a currently-running job."""
        job = self.jobs.remove(exec_file)
        self._log_audit_message(f'Removed job: {job.exec_file}')
        print(f'Job {job.exec_file} has been removed from the queue for future execution.')
        if self.current_job.get() == exec_file:
            print('This job is running. The current run has NOT been terminated.')

    def resume_job(self, exec_file, next_run_time=None):
        """Resume a job that was suspended due to an error.

        If next_run_time is not None, it will be used as the new next_run_time,
        otherwise the previous run-time will be used. 'now' can be used to
        run the job immediately."""
        if next_run_time is None:
            # don't specify next_run_time to use the old value
            self.jobs.update(exec_file, status=STATUS_QUEUED)
        else:
            self.jobs.update(exec_file, status=STATUS_QUEUED, next_run_time=next_run_time)
        print('Job {} has been placed in the active job queue.'.format(exec_file))
        if self.is_running():
            self._awaken_daemon()
        else:
            print('NOTE: The job-runner is NOT CURRENTLY RUNNING. Until it is started again, this job WILL NOT BE RUN.')

    def purge(self):
        """Remove all jobs that have no scheduled runs remaining."""
        jobs = self.jobs.get_jobs()
        for job in jobs:
            if job.status == STATUS_QUEUED and job.next_run_time is None:
                self.jobs.remove(job.exec_file)
                self._log_audit_message(f'Purged job: {job.exec_file}')
                print(f'Purged: {job.exec_file}')

    def resume_all(self):
        """Resume all jobs that are in the error state."""
        jobs = self.jobs.get_jobs()
        for job in jobs:
            if job.status == STATUS_ERROR:
                print('Resuming job {}.'.format(job.exec_file))
                self.jobs.update(job.exec_file, status=STATUS_QUEUED)
        if self.is_running():
            self._awaken_daemon()
        else:
            print('NOTE: The job-runner is NOT CURRENTLY RUNNING. Until it is started again, jobs WILL NOT BE RUN.')

    def status(self):
        """Print a status message listing the running and queued jobs, if any."""
        is_running = self.is_running()
        if is_running:
            print('Job-runner daemon is running (PID {}).'.format(self.get_pid()))
            current_job = self.current_job.get()
        else:
            print('Job-runner daemon is NOT running.')
            # In the unlikely event that the current_job file didn't get cleared before the daemon exited
            # we should just ignore any stale entries in current_job.
            current_job = None
        if current_job:
            print('Running job {}.'.format(current_job))
        jobs = self.jobs.get_jobs()
        upcoming_jobs = []
        non_queued_jobs = []
        for job in jobs:
            if job.exec_file == current_job:
                continue
            if job.status == STATUS_QUEUED and job.next_run_time is not None:
                upcoming_jobs.append(job)
            else:
                non_queued_jobs.append(job)
        if current_job and not upcoming_jobs:
            print('No other queued jobs.')
        elif not upcoming_jobs:
            print('No queued jobs.')
        else:
            print('Queued jobs:')
            if not is_running:
                print('NOTE: As the job-runner is NOT CURRENTLY RUNNING, queued jobs WILL NOT BE RUN until the runner is started.')
            for job in upcoming_jobs:
                print(self.format_job_blurb(job))
        if non_queued_jobs:
            print('Jobs not queued:')
            for job in non_queued_jobs:
                print(self.format_job_blurb(job))

    def format_job_blurb(self, job):
        if job.next_run_time is None:
            time_blurb = 'no additional runs scheduled'
        else:
            now = time.time()
            interval = (job.next_run_time - now)
            past = interval < 0
            if past:
                interval *= -1
            hours = int(interval // 60**2)
            minutes = int(interval % 60**2 // 60)
            seconds = int(interval % 60)
            timediff = ''
            if hours:
                timediff += str(hours) + 'h '
            if hours or minutes:
                timediff += str(minutes) + 'm '
            timediff += str(seconds) + 's'
            if past:
                time_blurb = 'scheduled for {} ago'.format(timediff)
            else:
                time_blurb = 'scheduled in {}'.format(timediff)
        return '{}: {} (status: {})'.format(time_blurb, job.exec_file, job.status)

    def start(self, verbose):
        super().start(self.log_dir, verbose, SIGINT=self.sigint_handler, SIGHUP=self.sighup_handler)

    def stop(self, message):
        """Gracefully terminate job daemon.

        Note: If a job is currently running, it will complete."""
        self.assert_daemon()
        self.signal(signal.SIGINT)
        self._log_audit_message(f'Requesting daemon stop: {message}')
        current_job = self.current_job.get()
        if current_job is not None:
            print('Waiting for job {} to complete.'.format(current_job))
        self.current_job.wait()
        if current_job is not None:
            print('Job complete. Job-runner is stopping.')

    def terminate(self, message):
        self._log_audit_message(f'Terminating daemon: {message}')
        super().terminate()

    def duty_cycle(self, intervals=[6, 24, 24*7]):
        """Return job-running cycle over the previous number of hours specified."""
        logfiles = sorted(self.log_dir.glob('messages.log*')) # read all logs, including rotated ones
        completed_jobs = []
        for logfile in logfiles:
            # read text, skipping first char which is a >, then split job entries on
            # >s that start at new lines.
            log_entries = logfile.read_text()[1:].split('\n>')
            start_time = None
            for entry in log_entries:
                isotime, loglevel, module, message = entry.split('\t')
                timestamp = time.mktime(time.strptime(isotime, '%Y-%m-%d %H:%M:%S'))
                if message.startswith('Running job'):
                    start_time = timestamp
                elif message.startswith('Job done'):
                    if start_time is None:
                        # job logs shouldn't contain job stop but no job start...
                        print('Anomaly in job log {}: no start time for job done at {}'.format(logfile, isotime))
                        continue
                    elapsed_time = timestamp - start_time
                    completed_jobs.append((start_time, elapsed_time))
        duty_cycles = []
        for interval in intervals:
            start_threshold = time.time() - interval * 3600 # interval is in hours
            in_interval = [job[1] for job in completed_jobs if job[0] > start_threshold]
            job_hours = sum(in_interval) / 3600
            duty_cycle = int(100*job_hours / interval)
            duty_cycles.append((job_hours, duty_cycle))
            print('In the last {} hours, jobs ran for {:.1f} hours ({}%).'.format(interval, job_hours, duty_cycle))
        return duty_cycles

    def _awaken_daemon(self):
        """Wake the daemon up if it is sleeping, so that it will reread the
        job file."""
        self.signal(signal.SIGHUP)

    # FOLLOWING FUNCTIONS ARE FOR USE WHEN DAEMONIZED

    def sigint_handler(self, signal_number, stack_frame):
        """Stop running, but allow existing jobs to finish. If received twice,
        forcibly terminate."""
        logger.info('Caught SIGINT')
        if self.running:
            logger.info('Attempting to terminate gracefully.')
            self.running = False
            if self.asleep:
                raise InterruptedError()
        else: # not running: we already tried to end this
            logger.warning('Forcibly terminating.')
            raise SystemExit()

    def sighup_handler(self, signal_number, stack_frame):
        """If sleeping, break out of sleep."""
        logger.debug('Caught SIGHUP')
        if self.asleep:
            raise InterruptedError()

    def initialize_daemon(self):
        self.jobs.update_job_lock()
        self.current_job.clear()

    def run_daemon(self):
        """Main loop: get a job to run and run it, or sleep until the next run
        time (or forever) otherwise."""
        # upon restarting, try to run job_runner_check (in a subprocess, so if it breaks it's not our problem)
        # to send the all-clear email if there were previous alert emails
        job_runner_check = pathlib.Path(sys.argv[0]).parent / 'job_runner_check'
        if job_runner_check.exists():
            logger.debug('running job_runner_check')
            subprocess.run([str(job_runner_check)])
        self.asleep = False
        self.running = True
        logger.debug('starting job runner daemon mainloop')
        self._log_audit_message(f'Daemon started.')
        try:
            while self.running:
                self._run_job_or_sleep()
        finally:
            self._log_audit_message(f'Daemon exited.')

    def _run_job_or_sleep(self):
        job = self._get_next_job() # may be None
        if job and job.next_run_time > time.time():
            # not ready to run job yet
            sleep_time = job.next_run_time - time.time()
            job = None
        else:
            sleep_time = 60*60*24 # sleep for a day
        if job:
            # Run a job if there was one
            self.current_job.set(job)
            try:
                self._run_job(job)
            finally:
                self.current_job.clear()
        else:
            # if we're out of jobs, sleep for a while
            self.asleep = True
            logger.debug('Sleeping for {}s', sleep_time)
            try:
                time.sleep(sleep_time)
            except InterruptedError:
                logger.debug('Awoken by HUP')
            self.asleep = False

    def _run_job(self, job):
        """Actually run a given job and interpret the output"""
        logger.info('Running job {}', job.exec_file)
        # -u for unbuffered output -- necessary for _listen_for_heartbeats
        args = [sys.executable, '-u', str(job.exec_file), str(job.next_run_time)]
        logger.debug('Parameters: {}', args)
        start_time = time.time()
        sub = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        timed_out, retcode, stdout, stderr = _listen_for_heartbeats(sub)
        elapsed_time = time.time() - start_time
        logger.info('Job done (elapsed time: {:.0f} min)', elapsed_time/60)
        logger.debug('Stdout {}', stdout)
        logger.debug('Stderr {}', stderr)
        logger.debug('Retcode {}', retcode)
        if sub.returncode != 0:
            error_text = 'Calling: {}\nReturn code: {}\nStandard Error output:\n{}'.format(' '.join(args), sub.returncode, stderr)
            if timed_out:
                error_text = 'Job timed out after {} seconds (timeout interval: {} sec)\n'.format(int(elapsed_time), HEARTBEAT_TIMEOUT) + error_text
            self._job_broke(job, timed_out, error_text)
            return
        lines = stdout.rstrip().split('\n')
        last = lines[-1]
        if last.startswith('next run:'):
            try:
                next_run_time = float(last[9:])
            except Exception as e:
                self._job_broke(job, False, 'Could not parse next run time from job response "{}": {}'.format(last, e))
                return
        else:
            next_run_time = None
        try:
            self.jobs.update(job.exec_file, next_run_time=next_run_time)
        except ValueError:
            logger.info('Could not update job {}: perhaps it was removed while running?', job.exec_file)

        if next_run_time:
            logger.info('Next run time in {:.0f} seconds'.format(next_run_time - time.time()))
        else:
            logger.info('No further runs scheduled.')

    def _get_next_job(self):
        """Get the job that should be run next."""
        for job in self.jobs.get_jobs():
            if job.status == STATUS_QUEUED and job.next_run_time is not None:
                return job

    def _job_broke(self, job, timed_out, error_text, new_status=STATUS_ERROR):
        """Alert the world that the job errored out."""
        self.jobs.update(job.exec_file, status=new_status)
        error_type = 'timed out' if timed_out else 'failed'
        self._log_audit_message(f'Job {error_type}: {job.exec_file}')
        logger.error('Acquisition job {} {}:\n {}\n', job.exec_file, error_type, error_text)
        if job.alert_emails:
            subject = f'[{platform.node()}] Job {job.exec_file} {error_type}.'
            self.send_error_email(job.alert_emails, subject, error_text)

    @staticmethod
    def send_error_email(emails, subject, text):
        try:
            host = platform.node().split('.')[0]
        except:
            host = 'scope_job_runner'
        sender = f'{host}@zplab.wustl.edu'
        config = scope_configuration.get_config()
        message = mimetext.MIMEText(text)
        message['From'] = sender
        message['To'] = ', '.join(emails)
        message['Subject'] = subject
        try:
            with smtplib.SMTP(config.mail_relay) as s:
                s.sendmail(sender, emails, message.as_string())
        except:
            logger.error('Could not send alert email.', exc_info=True)


_Job = collections.namedtuple('Job', ('exec_file', 'alert_emails', 'next_run_time', 'status'))

def _listen_for_heartbeats(sub):
    stdout_fd = sub.stdout.fileno()
    stderr_fd = sub.stderr.fileno()
    open_fds = {stdout_fd, stderr_fd}
    output = {fd: b'' for fd in open_fds}
    last_heartbeat_end_pos = 0
    last_heartbeat = time.time()
    time_left = HEARTBEAT_TIMEOUT
    timed_out = False
    while open_fds:
        ready = select.select(open_fds, [], [], time_left)[0]
        for fd in ready:
            out = os.read(fd, 2048)
            if not out:
                # closed fd reports as ready, but has no data
                open_fds.remove(fd)
                continue
            output[fd] += out
            if fd == stdout_fd:
                pos = output[fd].rfind(HEARTBEAT_BYTES, last_heartbeat_end_pos)
                if pos != -1:
                    last_heartbeat_end_pos = pos + len(HEARTBEAT_BYTES)
                    last_heartbeat = time.time()
        time_left = last_heartbeat + HEARTBEAT_TIMEOUT - time.time()
        if time_left < 0:
            timed_out = True
            sub.kill()
            time_left = 1 # small timeout for last output to get buffered for select
    retcode = sub.wait()
    stdout = output[stdout_fd].decode()
    stderr = output[stderr_fd].decode()
    return timed_out, retcode, stdout, stderr

def _validate_alert_emails(alert_emails):
    if alert_emails is None:
        return alert_emails
    if isinstance(alert_emails, str):
        alert_emails = (alert_emails,)
    for email in alert_emails:
        if not isinstance(email, str):
            raise ValueError('Email address {} must be a string.'.format(email))
    return alert_emails

def canonical_path(path):
    return pathlib.Path(path).expanduser().resolve()

class RLockFile(lockfile.LockFile):
    def __init__(self, path, timeout=None):
        super().__init__(path, threaded=False, timeout=timeout)
        self.acquisitions = 0

    def acquire(self, timeout=None):
        if not self.acquisitions:
            super().acquire(timeout)
        self.acquisitions += 1

    def release(self):
        if self.acquisitions: # if it's already zero, don't decrement, but allow the release() below, which will error out in the usual way
            self.acquisitions -= 1
        if not self.acquisitions:
            super().release()

class _JobList:
    """Manage a list of jobs that is always stored as a file on disk. No in-memory
    mutation is allowed, so this job list is effectively stateless."""
    def __init__(self, backingfile_path):
        self.backing_file = canonical_path(backingfile_path)
        self.update_job_lock()
        if not self.backing_file.exists():
            self._write({})

    def update_job_lock(self):
        """Re-create a new job-lock. Necessary after daemonization because the lockfile
        workes based on process PID, which changes after daemonization. So make a new
        lock object that knows about the new PID."""
        self.jobs_lock = RLockFile(str(self.backing_file))

    def _read(self):
        """Return dict mapping exec_file to full Job tuples, read from self.backing_file."""
        with self.jobs_lock, self.backing_file.open('r') as bf:
            job_list = json.load(bf)
        job_dict = {}
        for exec_file, *rest in job_list:
            exec_file = pathlib.Path(exec_file)
            job_dict[exec_file] = _Job(exec_file, *rest)
        return job_dict

    def _write(self, jobs):
        """Write Job tuples as json to self.backing_file."""
        job_list = [[str(exec_file)] + rest for exec_file, *rest in jobs.values()]
        with self.jobs_lock, self.backing_file.open('w') as bf:
            datafile.json_encode_legible_to_file(job_list, bf)

    def remove(self, exec_file):
        """Remove the job specified by exec_file from the list."""
        with self.jobs_lock: # lock is reentrant so it's OK to lock it here and in the _read/_write calls
            exec_file = canonical_path(exec_file)
            jobs = self._read()
            if exec_file in jobs:
                job = jobs.pop(exec_file)
                self._write(jobs)
            else:
                raise ValueError('No job queued for {}'.format(exec_file))
        return job

    def add(self, exec_file, alert_emails, next_run_time, status, check_exists=True):
        """Add a new job to the list.

        Parameters:
            exec_file: required path to existing file
            alert_emails: None, tuple-of-strings, or single string
            next_run_time: timestamp float, 'now' or None
            status: current job status
            check_exists: raise error if exec_file does not exist
        """
        exec_file = canonical_path(exec_file)
        if check_exists and not exec_file.exists():
            raise ValueError('Executable file {} does not exist.'.format(exec_file))
        alert_emails = _validate_alert_emails(alert_emails)
        if next_run_time is 'now':
            next_run_time = time.time()
        elif next_run_time is not None:
            next_run_time = float(next_run_time)

        with self.jobs_lock:
            jobs = self._read()
            job = _Job(exec_file, alert_emails, next_run_time, status)
            jobs[exec_file] = job
            self._write(jobs)
        return job


    def update(self, exec_file, **kws):
        """Update the values of an existing job. Any parameter not in keyword args
        will be copied from the old job."""
        with self.jobs_lock:
            old_job = self._get_job(exec_file)
            assert set(_Job._fields[1:]).issuperset(kws.keys()) # kws can include any known field but exec_file
            for field in _Job._fields: # make sure all fields, including exec_file, are in kws
                if field not in kws:
                    kws[field] = getattr(old_job, field)
            # don't check if the file exists: it's already in our database so we
            # need SOME way of changing its status (i.e. to error!)
            self.add(check_exists=False, **kws)

    def get_jobs(self):
        """Return a list of Job objects, sorted by their next_run_time attribute.

        Note: if next_run_time is None, the job will appear at the end of the list."""
        jobs = self._read()
        return sorted(jobs.values(), key=lambda job: job.next_run_time if job.next_run_time is not None else float('inf'))

    def _get_job(self, exec_file):
        """Get the Job specified by exec_file"""
        exec_file = canonical_path(exec_file)
        jobs = self._read()
        if exec_file in jobs:
            return jobs[exec_file]
        else:
            raise ValueError('No job queued for {}'.format(exec_file))

class _JobFile:
    def __init__(self, jobfile_path):
        self.job_file = canonical_path(jobfile_path)

    def get(self):
        """Return the contents of the job_file if it exists, else None."""
        if self.job_file.exists():
            with self.job_file.open('r') as f:
                return canonical_path(f.read())
        else:
            return None

    def set(self, job):
        """Write the given string to the jobfile."""
        with self.job_file.open('w') as f:
            f.write(str(job.exec_file))

    def clear(self):
        """Remove the jobfile if it exists."""
        if self.job_file.exists():
            self.job_file.unlink()

    def wait(self):
        """Wait until the jobfile has been cleared."""
        while self.job_file.exists():
            time.sleep(1)
