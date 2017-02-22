class Emilator(object):
    def __init__(self, view, function):
        self._view = view
        self._function = function
        self._state = {}
        self._segments = {}

    def map_memory(self, base=None, size=0x1000, flags=0):
        if base is None:
            base = self._find_available_segment(size)

        self._view.add_user_segment(base, size, 0, 0, flags)

        self._segments[base] = self._view.get_segment_at(base)

        return base

    def unmap_memory(self, base, size):
        segment = self._view_get_segment_at(base)

        # XXX track unmapping a part of a segment
        self._segments.remove(segment.start)

        self._view.remove_user_segment(base, size)

    def _find_available_segment(self, size=0x1000, align=1):
        new_segment = None
        current_address = 0
        max_address = 2**((self._function.arch.address_size + 1) * 8) - 1
        align_mask = 2**((self._function.arch.address_size + 1) * 8) - align

        while current_address < (max_address - size):
            segment = self._view.get_segment_at(current_address)

            if segment is not None:
                current_address = (segment.end + align) & align_mask
                continue

            segment_end = current_address + size - 1

            if self._view.get_segment_at(segment_end) is None:
                new_segment = current_address
                break

        return new_segment

