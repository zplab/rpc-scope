class Footpedal:
    def __init__(self, iotool):
        self._iotool = iotool

    def wait(self):
        self._iotool.start_program(self._iotool.commands.footpedal_wait())
        self._iotool.wait_for_program_done()
        