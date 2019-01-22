class UnimplementedError(Exception):
    pass

class MemoryAccessError(Exception):
    def __init__(self, *args, **kwargs):
        super(MemoryAccessError, self).__init__(*args)
        self.address = kwargs.get('address', None)

class UndefinedError(Exception):
    pass