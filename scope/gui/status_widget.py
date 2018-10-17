# This code is licensed under the MIT License (see LICENSE file for details)

import pathlib
import time
from PyQt5 import Qt

from . import device_widget
from ..simple_rpc import rpc_client

class StatusWidget(device_widget.DeviceWidget):
    @staticmethod
    def can_run(scope):
        return True

    PROPERTY_DEFAULTS = dict(running=False, queued_jobs=0, errored_jobs=0, duty_cycle=0, current_job=None)

    def __init__(self, scope, parent=None):
        super().__init__(scope, parent)
        self.setWindowTitle('Status')
        layout = Qt.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.server_label = Qt.QLabel()
        layout.addWidget(self.server_label)
        self.runner_label = Qt.QLabel()
        layout.addWidget(self.runner_label)
        self.current_label = Qt.QLabel()
        layout.addWidget(self.current_label)
        layout.addStretch()

        for name, default in self.PROPERTY_DEFAULTS.items():
            setattr(self, name, default)
            self.subscribe('scope.job_runner.'+name, self._get_updater(name), readonly=True)

        self.server_running = False
        self.latest_update = 0
        self.timer = Qt.QBasicTimer()
        self.timerEvent(None)

    def _get_updater(self, name):
        def property_updated(value):
            setattr(self, name, value)
            self.latest_update = time.time()
            self.server_running = True
            self.update_labels()
        return property_updated

    def update_labels(self):
        _label_text(self.server_label, 'Server', self.server_running)
        job_runner_running = self.server_running and self.running
        suffix = None
        if job_runner_running:
            suffix = f'{self.duty_cycle}% duty; {self.queued_jobs} queued'
            if self.errored_jobs > 0:
                suffix +=f'; <span style="font-weight: bold; color: red">{self.errored_jobs} errors</span>'
        _label_text(self.runner_label, 'Job Runner', job_runner_running, suffix)
        if not job_runner_running:
            self.current_label.setText('')
        elif self.current_job is None:
            self.current_label.setText('No job running.')
        else:
            job = pathlib.Path(self.current_job)
            self.current_label.setText(f'Running "{job.parent.parent.name}/{job.parent.name}".')

    def timerEvent(self, event):
        was_running = self.server_running
        sec_since_update = time.time() - self.latest_update
        if sec_since_update > 60:
            with self.scope._rpc_client.timeout_sec(0.5):
                try:
                    assert self._ping() == 'pong'
                    self.server_running = True
                    self.latest_update = time.time()
                except rpc_client.RPCError:
                    self.server_running = False
        if self.server_running:
            # server running: don't need fast updates
            self._start_timer(60)
        else:
            if was_running or self.latest_update == 0:
                # was just running and now stopped, or we've never yet seen it running
                self._start_timer(10)
            elif sec_since_update > 600:
                # server off for more than 10 mins: can back off on the fast updates
                self._start_timer(60)
        self.update_labels()

    def _start_timer(self, sec):
        self.timer.start(sec*1000, Qt.Qt.VeryCoarseTimer, self) # run self.timerEvent at the specified interval

def _label_text(label, prefix, status_ok=True, suffix=None):
    if status_ok:
        sign = '<span style="color: green">\N{black circle}</span>'
    else:
        sign = '<span style="color: red">\N{heavy multiplication x}</span>'

    if suffix is not None:
        suffix = f' ({suffix})'
    else:
        suffix = ''
    label.setText(f'{prefix}: {sign}{suffix}')