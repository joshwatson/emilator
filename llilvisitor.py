from bnilvisitor import BNILVisitor
import errors


class LLILVisitor(BNILVisitor):
    def __init__(self, **kwargs):
        super(LLILVisitor, self).__init__(**kwargs)
        self._hooks = {}

    def visit(self, expression):
        hook = self._hooks.get(expression.operation)

        if hook:
            if hook.type == 1:
                return hook(self, expression)

            else:
                hook(self, expression)

        result = super(LLILVisitor, self).visit(expression)

        if result is None:
            raise errors.UnimplementedError(expression)

        return result
