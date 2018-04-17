# This code is licensed under the MIT License (see LICENSE file for details)

from ..util import property_device
from ..util import timer
from .. import scope_job_runner

class JobRunner(property_device.PropertyDevice):
    _DESCRIPTION = 'job runner'

    def __init__(self, property_server=None, property_prefix=''):
        super().__init__(property_server, property_prefix)
        self._runner = scope_job_runner.JobRunner()
        if property_server:
            self._fast_timer_thread = timer.Timer(self._update_fast_properties, interval=60) # every minute
            self._slow_timer_thread = timer.Timer(self._update_slow_properties, interval=3600) # every hour

    def _update_fast_properties(self):
        self.get_running()
        self.get_jobs()
        self.get_current_job()

    def _update_slow_properties(self):
        self.get_duty_cycle()

    def get_jobs(self):
        # don't return incubator_check job...
        jobs = [job for job in self._runner.jobs.get_jobs() if job.exec_file.name != 'incubator_check']
        statuses = [job.status for job in jobs]
        self._update_property('queued_jobs', statuses.count(scope_job_runner.STATUS_QUEUED))
        self._update_property('errored_jobs', statuses.count(scope_job_runner.STATUS_ERROR))
        jobs_out = []
        for job in jobs:
            d = job._asdict()
            d['exec_file'] = str(d['exec_file'])
            jobs_out.append(d)
        return jobs_out

    def get_current_job(self):
        job = self._runner.current_job.get()
        if job is not None:
            job = str(job)
        self._update_property('current_job', job)
        return job

    def get_running(self):
        running = self._runner.is_running()
        self._update_property('running', running)
        return running

    def get_duty_cycle(self):
        job_hours, duty_cycle = self._runner.duty_cycle(intervals=[24])[0]
        self._update_property('duty_cycle', duty_cycle)
        return duty_cycle