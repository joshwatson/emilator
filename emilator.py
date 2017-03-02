import struct
from collections import defaultdict

from binaryninja import (
    BinaryView, LowLevelILFunction, SegmentFlag, LLIL_REG_IS_TEMP, Endianness,
    Architecture, LLIL_GET_TEMP_REG_INDEX, BinaryViewType
)

import errors
import handlers
import memory

fmt = {1: 'B', 2: 'H', 4: 'L', 8: 'Q'}

def sign_extend(value, bits):
    sign_bit = 1 << (bits - 1)
    return (value & (sign_bit - 1)) - (value & sign_bit)

class Emilator(object):
    def __init__(self, function, view=None):
        if not isinstance(function, LowLevelILFunction):
            raise TypeError('function must be a LowLevelILFunction')

        self._function = function

        if view is None:
            view = BinaryView()

        self._view = view

        self._regs = {}
        self._flags = {}
        self._memory = memory.Memory(function.arch.address_size)

        for segment in view.segments:
            self._memory.map(
                segment.start, segment.length, segment.flags,
                view.read(segment.start, segment.length)
            )

        self._function_hooks = defaultdict(list)
        self._instr_hooks = defaultdict(list)
        self.handlers = handlers.Handlers(self)
        self.instr_index = 0

    @property
    def function(self):
        return self._function

    @property
    def mapped_memory(self):
        return list(self._memory)

    @property
    def registers(self):
        return dict(self._regs)

    @property
    def function_hooks(self):
        return dict(self._function_hooks)

    @property
    def instr_hooks(self):
        return defaultdict(list, self._instr_hooks)

    def map_memory(self,
        start=None,
        length=0x1000,
        flags=SegmentFlag.SegmentReadable | SegmentFlag.SegmentWritable,
        data=None):
        return self._memory.map(start, length, flags, data)

    def unmap_memory(self, base, size):
        raise errors.UnimplementedError('Unmapping memory not implemented')

    def register_function_hook(self, function, hook):
        pass

    def register_instruction_hook(self, operand, hook):
        # These hooks will be fallen back on if LLIL_UNIMPLEMENTED
        # is encountered
        pass

    def unregister_function_hook(self, function, hook):
        pass

    def unregister_instruction_hook(self, operand, hook):
        pass

    def set_register_value(self, register, value):
        # If it's a temp register, just set the value no matter what.
        # Maybe this will be an issue eventually, maybe not.
        if (isinstance(register, (int, long)) and 
                LLIL_REG_IS_TEMP(register)):
            self._regs[register] = value

        arch = self._function.arch

        reg_info = arch.regs[register]

        # normalize value to be unsigned
        if value < 0:
            value = value + (1 << reg_info.size * 8)

        if 0 > value >= (1 << reg_info.size * 8):
            raise ValueError('value is out of range')

        if register == reg_info.full_width_reg:
            self._regs[register] = value
            return

        full_width_reg_info = arch.regs[reg_info.full_width_reg]
        full_width_reg_value = self._regs.get(full_width_reg_info.full_width_reg)

        # XXX: The RegisterInfo.extend field currently holds a string for
        #      for built-in Architectures.
        if (full_width_reg_value is None and
                (reg_info.extend == 'NoExtend' or
                 reg_info.offset != 0)):
            raise errors.UndefinedError(
                'Register {} not defined'.format(
                    reg_info.full_width_reg
                )
            )

        if reg_info.extend == 'ZeroExtendToFullWidth':
            full_width_reg_value = value

        elif reg_info.extend == 'SignExtendToFullWidth':
            full_width_reg_value = (
                (value ^ ((1 << reg_info.size * 8) - 1)) -
                ((1 << reg_info.size * 8) - 1) +
                (1 << full_width_reg_info.size * 8)
            )

        elif reg_info.extend == 'NoExtend':
            # mask off the value that will be replaced
            mask = (1 << reg_info.size * 8) - 1
            full_mask = (1 << full_width_reg_info.size * 8) - 1
            reg_bits = mask << (reg_info.offset * 8)

            full_width_reg_value &= full_mask ^ reg_bits
            full_width_reg_value |= value << reg_info.offset * 8

        self._regs[full_width_reg_info.full_width_reg] = full_width_reg_value


    def get_register_value(self, register):
        if (isinstance(register, int) and
                LLIL_REG_IS_TEMP(register)):
            reg_value = self._regs.get(register)

            if reg_value is None:
                raise errors.UndefinedError(
                    'Register {} not defined'.format(
                        LLIL_GET_TEMP_REG_INDEX(register)
                    )
                )

            return reg_value

        reg_info = self._function.arch.regs[register]

        full_reg_value = self._regs.get(reg_info.full_width_reg)

        if full_reg_value is None:
            raise errors.UndefinedError(
                'Register {} not defined'.format(
                    register
                )
            )

        if register == reg_info.full_width_reg:
            return full_reg_value

        mask = (1 << reg_info.size * 8) - 1
        reg_bits = mask << (reg_info.offset * 8)

        reg_value = (full_reg_value & reg_bits) >> (reg_info.offset * 8)

        return reg_value

    def set_flag_value(self, flag, value):
        pass

    def get_flag_value(self, flag):
        pass

    def read_memory(self, addr, length):
        if length not in fmt:
            raise ValueError('read length must be in (1,2,4,8)')

        # XXX: Handle sizes > 8 bytes
        pack_fmt = (
            # XXX: Endianness string bug
            '<' if self._function.arch.endianness == 'LittleEndian'
            else ''
        ) + fmt[length]

        if addr not in self._memory:
            raise errors.MemoryAccessError(
                'Address {:x} is not valid.'.format(addr)
            )

        try:
            return struct.unpack(
                pack_fmt, self._memory.read(addr, length)
            )[0]
        except:
            raise errors.MemoryAccessError(
                'Could not read memory at {:x}'.format(addr)
            )

    def write_memory(self, addr, data):
        # XXX: This is terribly implemented
        if addr not in self._memory:
            raise errors.MemoryAccessError(
                'Address {:x} is not valid.'.format(addr)
            )

        self._memory.write(addr, data)

    def execute_instruction(self):
        # Execute a the current IL instruction
        instruction = self._function[self.instr_index]

        # increment to next instruction (can be changed by instruction)
        self.instr_index += 1

        self.handlers[instruction.operation](instruction)

    def run(self):
        while True:
            try:
                yield self.execute_instruction()
            except IndexError:
                raise StopIteration()

    def _find_available_segment(self, size=0x1000, align=1):
        new_segment = None
        current_address = 0
        max_address = (1 << (self._function.arch.address_size * 8)) - 1
        align_mask = (1 << (self._function.arch.address_size * 8)) - align

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

if __name__ == '__main__':
    il = LowLevelILFunction(Architecture['x86_64'])
    emi = Emilator(il)

    emi.set_register_value('rbx', -1)

    print '[+] Mapping memory at 0x1000 (size: 0x1000)...'
    emi.map_memory(0x1000, flags=SegmentFlag.SegmentReadable)

    print '[+] Initial Register State:'
    for r, v in emi.registers.iteritems():
        print '\t{}:\t{:x}'.format(r, v)

    il.append(il.set_reg(8, 'rax', il.const(8, 0x1000)))
    il.append(il.store(4, il.reg(8, 'rax'), il.const(4, 0xbadf00d)))
    il.append(il.set_reg(8, 'rbx', il.load(8, il.reg(8, 'rax'))))

    print '[+] Instructions:'
    print '\t'+repr(il[0])
    print '\t'+repr(il[1])
    print '\t'+repr(il[2])

    print '[+] Executing instructions...'
    for i in emi.run():
        print '\tInstruction completed.'

    print '[+] Final Register State:'
    for r, v in emi.registers.iteritems():
        print '\t{}:\t{:x}'.format(r, v)
