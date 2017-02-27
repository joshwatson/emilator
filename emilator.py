from collections import defaultdict

import binaryninja

import errors
import handlers

def sign_extend(value, bits):
    sign_bit = 1 << (bits - 1)
    return (value & (sign_bit - 1)) - (value & sign_bit)

class Emilator(object):
    def __init__(self, function, view=None):
        if not isinstance(function, binaryninja.LowLevelILFunction):
            raise TypeError('function must be a LowLevelILFunction')

        self._function = function

        if view is None:
            view = binaryninja.BinaryView()

        self._view = view

        self._regs = {}
        self._flags = {}
        self._segments = {}
        self._function_hooks = defaultdict(list)
        self._instr_hooks = defaultdict(list)
        self.handlers = handlers.Handlers(self)
        self.instr_index = 0

    @property
    def function(self):
        return self._function

    @property
    def registers(self):
        return dict(self._regs)

    @property
    def function_hooks(self):
        return dict(self._function_hooks)

    @property
    def instr_hooks(self):
        return defaultdict(list, self._instr_hooks)

    def map_memory(self, base=None, size=0x1000, flags=0):
        if base is None:
            base = self._find_available_segment(size)

        self._view.add_user_segment(base, size, 0, 0, flags)

        self._segments[base] = self._view.get_segment_at(base)

        return base

    def unmap_memory(self, base, size):
        segment = self._view.get_segment_at(base)

        # XXX: track unmapping a part of a segment
        del self._segments[segment.start]

        # XXX: this doesn't actually seem to work right now.
        #      https://github.com/Vector35/binaryninja-api/issues/631
        self._view.remove_user_segment(base, size)

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
                binaryninja.LLIL_REG_IS_TEMP(register)):
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
                binaryninja.LLIL_REG_IS_TEMP(register)):
            reg_value = self._regs.get(register)

            if reg_value is None:
                raise errors.UndefinedError(
                    'Register {} not defined'.format(
                        binaryninja.LLIL_GET_TEMP_REG_INDEX(register)
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
    il = binaryninja.LowLevelILFunction(binaryninja.Architecture['x86_64'])
    emi = Emilator(il)

    emi.set_register_value('rbx', -1)

    print '[+] Initial Register State:'
    for r,v in emi.registers.iteritems():
        print '\t{}:\t{:x}'.format(r, v)

    il.append(il.set_reg(8, 'rax', il.const(8, 0xbadf00d)))
    il.append(il.set_reg(8, 'rbx', il.reg(8, 'rax')))

    print '[+] Instructions:'
    print '\t'+repr(il[0])
    print '\t'+repr(il[1])

    print '[+] Executing instructions...'
    for i in emi.run():
        print '\tInstruction completed.'

    print '[+] Final Register State:'
    for r,v in emi.registers.iteritems():
        print '\t{}:\t{:x}'.format(r, v)