# -*- coding: utf-8 -*-

import platform
import datetime
import time

from .. import scope_client
from .. import scope_job_runner

def main(scope_host='127.0.0.1'):
    runner = scope_job_runner.JobRunner()
    jobs = runner.jobs.get_jobs()
    to_email = set()
    for job in jobs:
        if job.status == scope_job_runner.STATUS_QUEUED and job.alert_emails:
            to_email.update(job.alert_emails)

    if to_email:
        # there's someone to alert, so let's see if there's an alert to send:
        scope, scope_properties = scope_client.client_main(scope_host)
        humidity, temperature = scope.humidity_controller.data
        target_humidity = scope.humidity_controller.target_humidity
        target_temperature = scope.temperature_controller.target_temperature
        errors = []
        if humidity > 96 or humidity > target_humidity + 5 or humidity < target_humidity - 10:
            errors.append('HUMIDITY DEVIATION')
        if temperature > target_temperature + 2 or temperature < target_temperature - 2:
            errors.append('TEMPERATURE DEVIATION')
        if errors:
            host = platform.node().split('.')[0]
            now = datetime.datetime.now()
            now = now.replace(microsecond=0)
            now = now.isoformat(' ')
            subject = '{}: {}'.format(host, ' AND '.join(errors))
            message = '{}\nMachine: {}\nCurrent temperature: {}°C\n Target temperature: {}°C\nCurrent humidity: {}%\n Target humidity: {}%\n'
            message = message.format(now, host, temperature, target_temperature, humidity, target_humidity)
            runner._send_error_email(sorted(to_email), subject, error_text)

    # ask to run again in 20 mins
    print(time.time() + 20*60)


if __name__ == '__main__':
    import sys
    main(*sys.argv[1:])