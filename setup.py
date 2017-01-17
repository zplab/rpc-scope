import setuptools

setuptools.setup(
    name = 'scope',
    version = '1.5',
    description = 'zplab microscope package',
    packages = setuptools.find_packages(),
    package_data = {'scope.gui':['limit_icons/*.svg']},
    scripts = ['scripts/scope_gui', 'scripts/scope_job_runner', 'scripts/scope_server']
)
