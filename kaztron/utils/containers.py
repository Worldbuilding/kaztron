from collections import OrderedDict


class FifoCache(OrderedDict):
    """ Fixed-size cache, evicting the oldest inserted item when full. """

    def __init__(self, maxsize=128, *args, **kwargs):
        self.maxsize = maxsize
        super().__init__(*args, **kwargs)

    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if len(self) > self.maxsize:
            self.popitem(last=False)
