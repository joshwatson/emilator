import bisect
from collections import namedtuple

from binaryninja import SegmentFlag

import errors

#MemoryRange = namedtuple('MemoryRange', ['start', 'length', 'flags', 'data'])

class MemoryRange(object):
    def __init__(self, start, length, flags=0, data=None):
        self.start = start
        self.length = length
        self.flags = flags

        if data is None:
            virtual_data = bytearray('\x00')*length
        else:
            virtual_data = bytearray(data) + ('\x00' * (length - len(data)))

        self.data = memoryview(virtual_data)

    def __cmp__(self, other):
        if isinstance(other, (int, long)):
            return cmp(self.start, other)

        start_cmp = cmp(self.start, other.start)
        if start_cmp == 0:
            return cmp(self.length, other.length)
        return start_cmp

    def __repr__(self):
        return '<MemoryRange: start={:x}, length={:x}, flags={}>'.format(
            self.start, self.length, self.flags
        )

class Memory(object):
    def __init__(self, address_size):
        if address_size not in (1, 2, 4, 8):
            raise ValueError('address_size must be 1, 2, 4, or 8.')
        self._address_size = address_size

        self._ranges = []

    def __contains__(self, address):
        range_index = bisect.bisect_left(self._ranges, address)

        if range_index > len(self._ranges):
            return False

        try:
            if self._ranges[range_index].start == address:
                return True
        except IndexError:
            return False

        if range_index == 0:
            return False

        try:
            prev_range = self._ranges[range_index - 1]
        except IndexError:
            return False

        if (prev_range.start < address and
                prev_range.length + prev_range.start > address):
            return True

        return False

    def __iter__(self):
        return iter(self._ranges)

    def read(self, address, length):
        # XXX: Handle split ranges
        idx = bisect.bisect_left(self._ranges, address)

        try:
            if self._ranges[idx].start > address:
                idx -= 1
        except IndexError:
            idx -= 1

        try:
            range = self._ranges[idx]
        except IndexError:
            raise errors.MemoryAccessError()

        if range.start <= address < range.length:
            if range.start + length > range.length:
                raise errors.MemoryAccessError(
                    '{[{:x},{:x}] is not valid range of memory'.format(
                        address, address+length
                    )
                )
        return range.data[address-range.start:address+length-range.start].tobytes()

    def write(self, address, value):
        length = len(value)

        # XXX: Handle split ranges
        idx = bisect.bisect_left(self._ranges, address)
        
        if self._ranges[idx].start > address:
            idx -= 1

        range = self._ranges[idx]

        if range.start <= address < range.length:
            if range.start + length > range.length:
                raise errors.MemoryAccessError(
                    '{[{:x},{:x}] is not valid range of memory'.format(
                        address, address+length
                    )
                )

        range.data[address-range.start:address+length-range.start] = value

    def map(self,
            start=None,
            length=0x1000,
            flags=SegmentFlag.SegmentReadable | SegmentFlag.SegmentWritable,
            data=None):
        if start is None:
            start = self._find_available_base(length)

        bisect.insort(self._ranges, MemoryRange(start, length, flags, data))

        return start

    def _find_available_base(self, length):
        max_address = (1 << self._address_size * 8) - 1

        if length > max_address:
            raise OverflowError(
                'length {} is larger than max address'.format(length)
            )

        # return 0 if available
        if self._ranges[0].start > length:
            return 0

        for i, range in self._ranges:
            next_start = range.start + range.length + 1
            next_end = next_start + length
            start_bisect = bisect.bisect_left(next_start)
            end_bisect = bisect.bisect_right(next_end)

            # if they are the same value, then this range is available
            if start_bisect == end_bisect and next_end < max_address:
                return next_start