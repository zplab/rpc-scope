# The MIT License (MIT)
#
# Copyright (c) 2014-2015 WUSTL ZPLAB
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Authors: Zach Pincus


import importlib
from .messaging import message_device
from .config import scope_configuration
from .util import property_device

from .util import logging
logger = logging.get_logger(__name__)

class Namespace:
    pass

class Scope(message_device.AsyncDeviceNamespace):
    def __init__(self, property_server=None):
        super().__init__()

        self._property_server = property_server
        if property_server is not None:
            self.rebroadcast_properties = property_server.rebroadcast_properties

        self._components = []

        self.get_configuration = scope_configuration.get_config
        config = self.get_configuration()
        for attr_name, component_class_path in config.drivers:
            module_name, class_name = component_class_path.rsplit('.', 1)
            module = importlib.import_module('.device.'+module_name, __package__)
            component_class = getattr(module, class_name)
            self.initialize_component(attr_name, component_class)

    def initialize_component(self, attr_name, component_class):
        kws = {}
        for kwarg, requires_class in component_class.__init__.__annotations__.items():
            # scope component classes require annotations for all dependencies in the
            # init function (except property server stuff, which is handled below)
            for extant_component in self._components:
                if isinstance(extant_component, requires_class):
                    kws[kwarg] = extant_component
                    break
            if kwarg not in kws:
                logger.warning('Could not initialize {}: requires {}', component_class.__name__, requires_class.__name__)
                return False

        if issubclass(component_class, property_device.PropertyDevice):
            kws['property_server'] = self._property_server
            property_path = ['scope'] + attr_name.split('.')
            filtered = [entry for entry in property_path if not entry.startswith('_')]
            kws['property_prefix'] = '.'.join(filtered) + '.'

        try:
            expected_errs = component_class._EXPECTED_INIT_ERRORS
        except AttributeError:
            expected_errs = ()

        try:
            description = component_class._DESCRIPTION
        except AttributeError:
            description = component_class.__name__

        if expected_errs:
            logger.info('Looking for {}...', description)
        try:
            component = component_class(**kws)
        except expected_errs:
            logger.log_exception('Could not connect to {}:'.format(description))
            return False
        owner = self
        *attr_path, name = attr_name.split('.')
        for elem in attr_path:
            if hasattr(owner, elem):
                owner = getattr(owner, elem)
            else:
                namespace = Namespace()
                setattr(owner, elem, namespace)
                owner = namespace
        setattr(owner, name, component)
        self._components.append(component)
        return True
