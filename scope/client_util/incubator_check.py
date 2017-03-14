# -*- coding: utf-8 -*-

import platform
import datetime
import time

from .. import scope_client
from .. import scope_job_runner
from ..config import scope_configuration

def main(scope_host='127.0.0.1'):
    runner = scope_job_runner.JobRunner()
    jobs = runner.jobs.get_jobs()
    to_email = set()
    for job in jobs:
        if job.status == scope_job_runner.STATUS_QUEUED and job.alert_emails:
            to_email.update(job.alert_emails)

    print('Concerned parties: {}'.format(', '.join(sorted(to_email))))

    if to_email:
        # there's someone to alert, so let's see if there's an alert to send:
        scope, scope_properties = scope_client.client_main(scope_host)
        humidity, temperature = scope.humidity_controller.data
        target_humidity = scope.humidity_controller.target_humidity
        target_temperature = scope.temperature_controller.target_temperature

        host = platform.node().split('.')[0]
        now = datetime.datetime.now()
        now = now.replace(microsecond=0)
        now = now.isoformat(' ')
        message = 'Machine: {}\nTime: {}\n\nActual temperature: {}°C\nTarget temperature: {}°C\n\nActual humidity: {}%\nTarget humidity: {}%\n'
        message = message.format(host, now, temperature, target_temperature, humidity, target_humidity)
        print(message)

        errors = []
        if humidity > 95 or abs(humidity - target_humidity) >= 10:
            errors.append('HUMIDITY DEVIATION')
        if abs(temperature - target_temperature) >= 2:
            errors.append('TEMPERATURE DEVIATION')
        if errors:
            subject = '{}: {}'.format(host, ' AND '.join(errors))

            last_email_file = scope_configuration.CONFIG_DIR / '.last_incubator_error_email_time'
            send_email = False
            if not last_email_file.exists():
                send_email = True
            else:
                with last_email_file.open() as f:
                    last_email = float(f.read())
                if time.time() > last_email + 6*60*60: # email every 6h at most
                    send_email = True
            if send_email:
                print('sending email: {}'.format(subject))
                runner._send_error_email(sorted(to_email), subject, message)
                with last_email_file.open('w') as f:
                    f.write(str(time.time()))
            else:
                print('not sending email (previous alert too recent)')

    # ask to run again in 20 mins
    print('next run:{}'.format(time.time() + 20*60))
