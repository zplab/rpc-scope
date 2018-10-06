# This code is licensed under the MIT License (see LICENSE file for details)

import setuptools

setuptools.setup(
    name = 'scope',
    version = '2',
    description = 'zplab microscope package',
    packages = setuptools.find_packages(),
    package_data = {'scope.gui': ['limit_icons/*.svg', 'icon.svg']},
    entry_points = {
        'console_scripts': [
            'scope_gui=scope.cli.scope_gui:main',
            'scope_monitor=scope.cli.scope_monitor:main',
            'scope_server=scope.cli.scope_server:main',
            'scope_job_runner=scope.cli.scope_job_runner:main',
            'incubator_check=scope.client_util.incubator_check:main',
            'job_runner_check=scope.client_util.job_runner_check:main'
        ],
    }
)
