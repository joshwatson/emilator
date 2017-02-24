import math

import exceptions

def sign_extend(value, bits):
    sign_bit = 1 << (bits - 1)
    return (value & (sign_bit - 1)) - (value & sign_bit)

class Emilator(object):
    def __init__(self, view, function):
        self._view = view
        self._function = function
        self._regs = {}
        self._flags = {}
        self._segments = {}
        self._function_hooks = {}
        self._instr_hooks = {}

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
        reg_info = self._view.arch.regs[register]

        # normalize value to be unsigned
        if value < 0:
            value = value + (1 << reg_info.size * 8)

        if 0 > value >= (1 << reg_info.size * 8):
            raise ValueError('value is out of range')

        if register == reg_info.full_width_reg:
            self._regs[register] = value
            return

        full_width_reg_info = self._view.arch.regs[reg_info.full_width_reg]
        full_width_reg_value = self._regs.get(full_width_reg_info.full_width_reg)

        # XXX: The RegisterInfo.extend field currently holds a string for
        #      for built-in Architectures.
        if (full_width_reg_value is None and
                (reg_info.extend == 'NoExtend' or
                 reg_info.offset != 0)):
            raise exceptions.UndefinedError(
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
        reg_info = self._view.arch.regs[register]

        full_reg_value = self._regs.get(reg_info.full_width_reg)

        if full_reg_value is None:
            raise exceptions.UndefinedError(
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

    def execute(self, instr_index):
        # Start execution from a given IL instruction address.
        pass

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

