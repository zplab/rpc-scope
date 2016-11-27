import distutils.core

distutils.core.setup(name='scope',
    version='1.0',
    description='zplab microscope package',
    packages=['scope', 'scope.cli', 'scope.client_util', 'scope.config',
        'scope.device',  'scope.device.andor', 'scope.device.iotool',
        'scope.device.leica', 'scope.gui', 'scope.messaging', 'scope.simple_rpc',
        'scope.timecourse', 'scope.util'],
    scripts=['scripts/scope_gui', 'scripts/scope_job_runner', 'scripts/scope_server']
    )
