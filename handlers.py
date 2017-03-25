import struct
from types import FunctionType

from binaryninja import LowLevelILOperation as Op
from collections import defaultdict

class Handlers(object):
    _handlers = defaultdict(
        lambda: lambda i,j: (_ for _ in ()).throw(NotImplementedError(i.operation))
    )

    def __init__(self, emilator):
        self.emilator = emilator

    @classmethod
    def add(cls, operation):
        def add_decorator(handler):
            cls._handlers[operation] = handler
            return handler
        return add_decorator

    def __getitem__(self, op):
        hooks = self.emilator.instr_hooks[op]
        handler = self._handlers[op]

        def call_hooks(expr):
            for hook in hooks:
                hook(expr, self.emilator)

            try:
                return handler(expr, self.emilator)
            except NotImplementedError:
                if not hooks:
                    raise

        return call_hooks


@Handlers.add(Op.LLIL_SET_REG)
def _set_reg(expr, emilator):
    value = emilator.handlers[expr.src.operation](expr.src)
    emilator.set_register_value(expr.dest, value)

@Handlers.add(Op.LLIL_CONST)
def _const(expr, emilator):
    return expr.value

@Handlers.add(Op.LLIL_REG)
def _reg(expr, emilator):
    return emilator.get_register_value(expr.src)

@Handlers.add(Op.LLIL_LOAD)
def _load(expr, emilator):
    addr = emilator.handlers[expr.src.operation](expr.src)

    return emilator.read_memory(addr, expr.size)

@Handlers.add(Op.LLIL_STORE)
def _store(expr, emilator):
    addr = emilator.handlers[expr.dest.operation](expr.dest)
    value = emilator.handlers[expr.src.operation](expr.src)

    emilator.write_memory(addr, value, expr.size)

@Handlers.add(Op.LLIL_PUSH)
def _push(expr, emilator):
    sp = emilator.function.arch.stack_pointer

    value = emilator.handlers[expr.src.operation](expr.src)

    sp_value = emilator.get_register_value(sp)

    emilator.write_memory(sp_value, value, expr.size)

    sp_value += expr.size

    emilator.set_register_value(sp, sp_value)

@Handlers.add(Op.LLIL_POP)
def _pop(expr, emilator):
    sp = emilator.function.arch.stack_pointer

    sp_value = emilator.get_register_value(sp)

    sp_value -= expr.size

    value = emilator.read_memory(sp_value, expr.size)

    emilator.set_register_value(sp, sp_value)

    return value

@Handlers.add(Op.LLIL_GOTO)
def _goto(expr, emilator):
    emilator.instr_index = expr.dest

@Handlers.add(Op.LLIL_IF)
def _if(expr, emilator):
    condition = emilator.handlers[expr.condition.operation](expr.condition)

    if condition:
        emilator.instr_index = expr.true
    else:
        emilator.instr_index = expr.false

@Handlers.add(Op.LLIL_CMP_NE)
def _cmp_ne(expr, emilator):
    left = emilator.handlers[expr.left.operation](expr.left)
    right = emilator.handlers[expr.right.operation](expr.right)

    return left != right

@Handlers.add(Op.LLIL_CMP_E)
def _cmp_e(expr, emilator):
    left = emilator.handlers[expr.left.operation](expr.left)
    right = emilator.handlers[expr.right.operation](expr.right)

    return left == right

@Handlers.add(Op.LLIL_ADD)
def _add(expr, emilator):
    left = emilator.handlers[expr.left.operation](expr.left)
    right = emilator.handlers[expr.right.operation](expr.right)

    return left + right

@Handlers.add(Op.LLIL_RET)
def _ret(expr, emilator):
    raise StopIteration