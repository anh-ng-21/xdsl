from __future__ import annotations
from xdsl.printer import Printer
from xdsl.ir import *
from xdsl.irdl import *
from xdsl.util import *
from xdsl.dialects.memref import *
from xdsl.dialects.builtin import IntegerType, Float32Type, IntegerAttr, FlatSymbolRefAttr
from xdsl.parser import Parser


@dataclass
class Rise:
    ctx: MLContext

    def __post_init__(self):
        self.ctx.register_attr(NatAttr)
        self.ctx.register_attr(ArrayType)
        self.ctx.register_attr(ScalarType)
        self.ctx.register_attr(TupleType)
        self.ctx.register_attr(FunType)

        self.ctx.register_op(In)
        self.ctx.register_op(Fst)
        self.ctx.register_op(Snd)
        self.ctx.register_op(Tuple)
        self.ctx.register_op(Zip)
        self.ctx.register_op(Map)
        self.ctx.register_op(Reduce)
        self.ctx.register_op(Lambda)
        self.ctx.register_op(Apply)
        self.ctx.register_op(Embed)
        self.ctx.register_op(Return)
        self.ctx.register_op(Literal)
        self.ctx.register_op(LoweringUnit)

    def nat(self, value: int) -> NatAttr:
        return NatAttr.from_int(value)

    def array(self, size: Union[int, NatAttr], elemT: DataType):
        if isinstance(size, int):
            size = NatAttr.from_int(size)
        return ArrayType.from_length_and_elemT(size, elemT)

    def scalar(self, wrapped: Attribute):
        return ScalarType.from_wrapped_type(wrapped)

    def tuple(self, left: DataType, right: DataType):
        return TupleType.from_types(left, right)

    def fun(self, left: Union[RiseType, DataType], right: Union[RiseType,
                                                                DataType]):
        return FunType.from_types(left, right)

    def inOp(self, value: Union[Operation, SSAValue],
             type: DataType) -> Operation:
        return In.create([SSAValue.get(value)], [type], {"type": type})

    def out(self, input: Union[Operation, SSAValue],
            output: Union[Operation, SSAValue]) -> Operation:
        return Out.create([SSAValue.get(input), SSAValue.get(output)])

    def zip(self, n: NatAttr, s: DataType, t: DataType) -> Operation:
        return Zip.create([],
                          result_types=[
                              self.fun(
                                  self.array(n, s),
                                  self.fun(self.array(n, t),
                                           self.array(n, self.tuple(s, t))))
                          ],
                          attributes={
                              "n": n,
                              "s": s,
                              "t": t
                          })

    def tupleOp(self, s: DataType, t: DataType) -> Operation:
        return Tuple.create(
            [],
            result_types=[self.fun(s, self.fun(t, self.tuple(s, t)))],
            attributes={
                "s": s,
                "t": t
            })

    def fst(self, s: DataType, t: DataType) -> Operation:
        return Fst.create([],
                          result_types=[self.fun(self.tuple(s, t), s)],
                          attributes={
                              "s": s,
                              "t": t
                          })

    def snd(self, s: DataType, t: DataType) -> Operation:
        return Snd.create([],
                          result_types=[self.fun(self.tuple(s, t), t)],
                          attributes={
                              "s": s,
                              "t": t
                          })

    def map(self, n: NatAttr, s: DataType, t: DataType) -> Operation:
        return Map.create([],
                          result_types=[
                              self.fun(
                                  self.fun(s, t),
                                  self.fun(self.array(n, s), self.array(n, t)))
                          ],
                          attributes={
                              "n": n,
                              "s": s,
                              "t": t
                          })

    def reduce(self, n: NatAttr, s: DataType, t: DataType) -> Operation:
        return Reduce.create([],
                             result_types=[
                                 self.fun(
                                     self.fun(s, self.fun(t, t)),
                                     self.fun(t, self.fun(self.array(n, s),
                                                          t)))
                             ],
                             attributes={
                                 "n": n,
                                 "s": s,
                                 "t": t
                             })

    def apply(self, fun: Union[Operation, SSAValue],
              *args: Union[Operation, SSAValue]) -> Operation:
        return Apply.create(
            [SSAValue.get(fun), *[SSAValue.get(arg) for arg in args]],
            [SSAValue.get(fun).typ.get_output_recursive()])

    def _lambda(self, block: Block) -> Operation:
        # build type of lambda
        assert (isinstance(block.ops[-1], Return))
        type = SSAValue.get(block.ops[-1].operands[0]).typ
        for arg in reversed(block.args):
            type = FunType.from_types(arg.typ, type)
        return Lambda.create([], [type], [], [],
                             regions=[Region.from_block_list([block])])

    def embed(self, *args: Union[Operation, SSAValue], resultType: Attribute,
              block: Block) -> Operation:
        # assert (len(block.args) == args.count)
        return Embed.create([SSAValue.get(arg) for arg in args], [resultType],
                            [], [],
                            regions=[Region.from_block_list([block])])

    def _return(self, value: Union[Operation, SSAValue]) -> Operation:
        return Return.create([value.results[0]])

    # to do this properly the float additions in the open PR are required
    def literal(self, value: int, type: Attribute):
        return Literal.create([], [f32],
                              {"value": IntegerAttr.from_params(value, type)})

    def lowering_unit(self, region: Block) -> Operation:
        return LoweringUnit.create([], [], [], [],
                                   regions=[Region.from_block_list([region])])


############### rise type system ###############


@irdl_attr_definition
class NatAttr(Data):
    name = "nat"
    data: int

    @staticmethod
    def parse(parser: Parser) -> NatAttr:
        data = parser.parse_int_literal()
        return NatAttr(data)

    def print(self, printer: Printer) -> None:
        printer.print_string(f'{self.data}')

    @staticmethod
    @builder
    def from_int(data: int) -> NatAttr:
        return NatAttr(data)


@irdl_attr_definition
class DataType(ParametrizedAttribute):
    name = ...
    data = ...


@irdl_attr_definition
class ArrayType(DataType):
    name = "rise.array"
    size = ParameterDef(NatAttr)
    elemType = ParameterDef(DataType)

    @staticmethod
    @builder
    def from_length_and_elemT(size: NatAttr, type: DataType) -> ArrayType:
        return ArrayType([size, type])


@irdl_attr_definition
class ScalarType(DataType):
    name = "scalar"
    wrapped = ParameterDef(Attribute)

    @staticmethod
    @builder
    def from_wrapped_type(type: Attribute) -> ScalarType:
        return ScalarType([type])


@irdl_attr_definition
class TupleType(DataType):
    name = "tuple"
    left = ParameterDef(DataType)
    right = ParameterDef(DataType)

    @staticmethod
    @builder
    def from_types(left: DataType, right: DataType) -> TupleType:
        return TupleType([left, right])


@irdl_attr_definition
class RiseType(ParametrizedAttribute):
    name = ...
    data = ...


@irdl_attr_definition
class FunType(RiseType):
    name = "rise.fun"
    input = ParameterDef(AnyOf([RiseType, DataType]))
    output = ParameterDef(AnyOf([RiseType, DataType]))

    @staticmethod
    @builder
    def from_types(input: Union[RiseType, DataType],
                   output: Union[RiseType, DataType]) -> FunType:
        return FunType([input, output])

    def get_output_recursive(self):
        type = self.output
        while isinstance(type, FunType):
            type = type.parameters[1]
        return type


############### rise operations ###############


@irdl_op_definition
class In(Operation):
    name: str = "rise.in"
    input = OperandDef(Attribute)
    type = AttributeDef(DataType)

    output = ResultDef(DataType)


@irdl_op_definition
class Out(Operation):
    name: str = "rise.out"
    input = OperandDef(Attribute)
    output = OperandDef(Attribute)


@irdl_op_definition
class Zip(Operation):
    name: str = "rise.zip"
    n = AttributeDef(NatAttr)
    s = AttributeDef(DataType)
    t = AttributeDef(DataType)

    output = ResultDef(FunType)


@irdl_op_definition
class Tuple(Operation):
    name: str = "rise.tuple"
    s = AttributeDef(DataType)
    t = AttributeDef(DataType)

    output = ResultDef(FunType)


@irdl_op_definition
class Fst(Operation):
    name: str = "rise.fst"
    s = AttributeDef(DataType)
    t = AttributeDef(DataType)

    output = ResultDef(FunType)


@irdl_op_definition
class Snd(Operation):
    name: str = "rise.snd"
    s = AttributeDef(DataType)
    t = AttributeDef(DataType)

    output = ResultDef(FunType)


@irdl_op_definition
class Map(Operation):
    name: str = "rise.map"
    n = AttributeDef(NatAttr)
    s = AttributeDef(DataType)
    t = AttributeDef(DataType)

    output = ResultDef(FunType)


@irdl_op_definition
class Reduce(Operation):
    name: str = "rise.reduce"
    n = AttributeDef(NatAttr)
    s = AttributeDef(DataType)
    t = AttributeDef(DataType)

    output = ResultDef(FunType)


@irdl_op_definition
class Lambda(Operation):
    name: str = "rise.lambda"

    body = SingleBlockRegionDef()
    output = ResultDef(FunType)


@irdl_op_definition
class Apply(Operation):
    name: str = "rise.apply"

    fun = OperandDef(FunType)
    args = VarOperandDef(Attribute)

    output = ResultDef(DataType)


@irdl_op_definition
class Embed(Operation):
    name: str = "rise.embed"
    args = VarOperandDef(Attribute)
    body = SingleBlockRegionDef()
    output = ResultDef(Attribute)


@irdl_op_definition
class Return(Operation):
    name: str = "rise.return"
    value = OperandDef(Attribute)


@irdl_op_definition
class Literal(Operation):
    name: str = "rise.literal"
    value = AttributeDef(AnyAttr())
    output = ResultDef(AnyAttr())


@irdl_op_definition
class LoweringUnit(Operation):
    name: str = "rise.lowering_unit"
    region = SingleBlockRegionDef()


@dataclass
class RiseBuilder:
    ctx: MLContext
    # insertion_point: Tuple[Block, int] = (None, 0)
    current_block: Block = None

    def _attach(self, op):
        if self.current_block is None:
            return
        self.current_block.insert_op(op, len(self.current_block.ops))

    def getSSAValue(self, opList) -> SSAValue:
        # last op in the list is the one we want. usually the apply
        if isinstance(opList, List):
            opList = opList[-1]
        return SSAValue.get(opList)

    def nat(self, value: int) -> NatAttr:
        return NatAttr.from_int(value)

    def array(self, size: Union[int, NatAttr], elemT: DataType):
        if isinstance(size, int):
            size = NatAttr.from_int(size)
        return ArrayType.from_length_and_elemT(size, elemT)

    def scalar(self, wrapped: Attribute):
        return ScalarType.from_wrapped_type(wrapped)

    def tuple(self, left: DataType, right: DataType):
        return TupleType.from_types(left, right)

    def fun(self, left: Union[RiseType, DataType], right: Union[RiseType,
                                                                DataType]):
        return FunType.from_types(left, right)

    def inOp(self, value: Union[Operation, SSAValue],
             type: DataType) -> Operation:
        op = In.create([self.getSSAValue(value)], [type], {"type": type})
        self._attach(op)
        return op

    def out(self, input: Union[Operation, SSAValue],
            output: Union[Operation, SSAValue]) -> Operation:
        op = Out.create([self.getSSAValue(input), self.getSSAValue(output)])
        self._attach(op)
        return op

    def apply(self, fun: Union[Operation, SSAValue],
              *args: Union[Operation, SSAValue]) -> Operation:
        op = Apply.create(
            [self.getSSAValue(fun), *[self.getSSAValue(arg) for arg in args]],
            [self.getSSAValue(fun).typ.get_output_recursive()])
        self._attach(op)
        return op

    def zip(self, left: Union[Operation, SSAValue],
            right: Union[Operation, SSAValue]) -> Operation:
        left = self.getSSAValue(left)
        right = self.getSSAValue(right)

        assert (isinstance(left.typ, ArrayType)
                & isinstance(right.typ, ArrayType))

        assert (left.typ.size == right.typ.size)
        n = left.typ.size
        s = left.typ.elemType
        t = right.typ.elemType

        zip = Zip.create([],
                         result_types=[
                             self.fun(
                                 self.array(n, s),
                                 self.fun(self.array(n, t),
                                          self.array(n, self.tuple(s, t))))
                         ],
                         attributes={
                             "n": n,
                             "s": s,
                             "t": t
                         })
        self._attach(zip)
        apply = self.apply(zip, left, right)
        return [zip, apply]

    def tupleOp(self, left: Union[Operation, SSAValue],
                right: Union[Operation, SSAValue]) -> list(Operation):
        left = self.getSSAValue(left)
        right = self.getSSAValue(right)
        assert (isinstance(left.typ, ArrayType)
                & isinstance(right.typ, ArrayType))
        s = left.typ.elemType
        t = right.typ.elemType

        tuple = Tuple.create(
            [],
            result_types=[self.fun(s, self.fun(t, self.tuple(s, t)))],
            attributes={
                "s": s,
                "t": t
            })
        self._attach(tuple)
        apply = self.apply(tuple, left, right)
        return [tuple, apply]

    def fst(self, value: Union[Operation, SSAValue]) -> list(Operation):
        assert (isinstance(value.typ, TupleType))
        value = self.getSSAValue(value)
        s = value.typ.left
        t = value.typ.right
        fst = Fst.create([],
                         result_types=[self.fun(self.tuple(s, t), s)],
                         attributes={
                             "s": s,
                             "t": t
                         })
        self._attach(fst)
        apply = self.apply(fst, value)
        return [fst, apply]

    def snd(self, value: Union[Operation, SSAValue]) -> list(Operation):
        assert (isinstance(value.typ, TupleType))
        value = self.getSSAValue(value)
        s = value.typ.left
        t = value.typ.right
        snd = Snd.create([],
                         result_types=[self.fun(self.tuple(s, t), t)],
                         attributes={
                             "s": s,
                             "t": t
                         })
        self._attach(snd)
        apply = self.apply(snd, value)
        return [snd, apply]

    def map(self, _lambda: Union[Operation, SSAValue],
            array: Union[Operation, SSAValue]) -> list(Operation):
        _lambda = self.getSSAValue(_lambda)
        array = self.getSSAValue(array)
        assert (isinstance(array.typ, ArrayType))
        n = array.typ.size
        s = array.typ.elemType
        lambdaOutputType = _lambda.typ.get_output_recursive()
        assert (isinstance(lambdaOutputType, ArrayType))
        t = lambdaOutputType.elemType
        map = Map.create([],
                         result_types=[
                             self.fun(
                                 self.fun(s, t),
                                 self.fun(self.array(n, s), self.array(n, t)))
                         ],
                         attributes={
                             "n": n,
                             "s": s,
                             "t": t
                         })
        self._attach(map)
        apply = self.apply(map, _lambda, array)
        return [_lambda, map, apply]

    def reduce(
        self, init: Union[Operation, SSAValue],
        array: Union[Operation, SSAValue], lambda_arg_types: List[Attribute],
        body: Callable[[BlockArgument, ...],
                       List[Operation]]) -> list(Operation):
        init = self.getSSAValue(init)
        array = self.getSSAValue(array)
        assert (isinstance(array.typ, ArrayType))
        n = array.typ.size
        s = array.typ.elemType
        _lambda = self._lambda(lambda_arg_types, body)
        t = self.getSSAValue(_lambda).typ.get_output_recursive()
        reduce = Reduce.create([],
                               result_types=[
                                   self.fun(
                                       self.fun(s, self.fun(t, t)),
                                       self.fun(t,
                                                self.fun(self.array(n, s), t)))
                               ],
                               attributes={
                                   "n": n,
                                   "s": s,
                                   "t": t
                               })
        self._attach(reduce)
        apply = self.apply(reduce, _lambda, init, array)
        return [_lambda, reduce, apply]

    def _lambda(
            self, lambda_arg_types: List[Attribute],
            body: Callable[[BlockArgument, ...],
                           List[Operation]]) -> Operation:
        saveCurrentBlock = self.current_block
        block = Block.from_arg_types(lambda_arg_types)
        self.current_block = block
        body(*block.args)
        self.current_block = saveCurrentBlock

        # build type of lambda
        assert (isinstance(block.ops[-1], Return))
        type = SSAValue.get(block.ops[-1].operands[0]).typ
        for arg in reversed(block.args):
            type = FunType.from_types(arg.typ, type)
        lambdaOp = Lambda.create([], [type], [], [],
                                 regions=[Region.from_block_list([block])])
        self._attach(lambdaOp)

        return lambdaOp

    def embed(self, *args: Union[Operation, SSAValue], resultType: Attribute,
              block: Block) -> Operation:
        # assert (len(block.args) == args.count)
        embedOp = Embed.create([self.getSSAValue(arg) for arg in args],
                               [resultType], [], [],
                               regions=[Region.from_block_list([block])])
        self._attach(embedOp)
        return embedOp

    def _return(self, value: Union[Operation, SSAValue]) -> Operation:
        returnOp = Return.create([value.results[0]])
        self._attach(returnOp)
        return returnOp

    # to do this properly the float additions in the open PR are required
    def literal(self, value: int, type: Attribute) -> Operation:
        literalOp = Literal.create(
            [], [f32], {"value": IntegerAttr.from_params(value, type)})
        self._attach(literalOp)
        return literalOp

    def lowering_unit(
            self, body: Callable[[BlockArgument, ...],
                                 List[Operation]]) -> Operation:
        flatten_list = lambda irregular_list: [
            element for item in irregular_list
            for element in Block.flatten_list(item)
        ] if type(irregular_list) is list else [irregular_list]

        self.current_block = Block.from_arg_types([])
        body()

        op = LoweringUnit.create(
            [], [], [], [],
            regions=[Region.from_block_list([self.current_block])])

        return op