class Condition:
    def __init__(self):
        self.condition = False

    def __bool__(self):
        return self.condition

    def __enter__(self):
        self.condition = True

    def __exit__(self, *exc_info):
        self.condition = False
