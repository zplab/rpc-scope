class PropertyDevice:
    def __init__(self, property_server, property_prefix):
        self._property_server = property_server
        self._property_prefix = property_prefix
    
    def _update_property(self, name, value):
        if self._property_server:
            self._property_server.update_property(self._property_prefix+name, value)
    
    def _add_property(self, name, initial_value):
        if self._property_server:
            return self._property_server.add_property(self._property_prefix+name, initial_value)
        else:
            return lambda x: None
        