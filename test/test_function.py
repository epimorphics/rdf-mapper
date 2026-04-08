
import unittest

from rdflib import Dataset, Literal
from typing_extensions import ChainMap

from rdf_mapper.lib.function import evaluate, get, register
from rdf_mapper.lib.mapper_spec import MapperSpec
from rdf_mapper.lib.template_state import TemplateState


class TestFunctionRegistry(unittest.TestCase):
    def test_register_and_get(self) -> None:
        def test_func(value, state, arg1) -> Literal:
            return Literal(f"{value} {arg1}")
        register("test_func", test_func)
        fn = get("test_func")
        self.assertEqual(fn(Literal("Hello"), TemplateState(ChainMap(), Dataset(), MapperSpec()), "World"), Literal("Hello World"))

    def test_get_with_args(self) -> None:
        def test_func(value, state, arg1) -> Literal:
            return Literal(f"{value} {arg1}")
        register("test_func", test_func)
        result = evaluate("test_func('World')", Literal("Hello"), TemplateState(ChainMap(), Dataset(), MapperSpec()))
        self.assertEqual(result, Literal("Hello World"))

    def test_get_with_variable_arg(self) -> None:
        def test_func(value, state, arg1) -> Literal:
            return Literal(f"{value} {arg1}")
        register("test_func", test_func)
        result = evaluate("test_func(greeting)", Literal("Hello"), TemplateState(ChainMap({"greeting": "Hi"}), Dataset(), MapperSpec()))
        self.assertEqual(result, Literal("Hello Hi"))

    def test_eval_with_global_function_no_params(self) -> None:
        result = evaluate("asInt3", '5', TemplateState(ChainMap(), Dataset(), MapperSpec()))
        self.assertEqual(result, 15)

    def test_eval_with_global_function_with_string_param(self) -> None:
        result = evaluate("split(',|:')", 'a,b:c', TemplateState(ChainMap(), Dataset(), MapperSpec()))
        self.assertEqual(result, ['a', 'b', 'c'])

    def test_eval_with_global_function_with_variable_param(self) -> None:
        result = evaluate("split(delimiter)", 'a,b:c', TemplateState(ChainMap({"delimiter": ",|:"}), Dataset(), MapperSpec()))
        self.assertEqual(result, ['a', 'b', 'c'])


class TestBuiltins(unittest.TestCase):
    def test_slug(self) -> None:
        self.assertEqual(evaluate("slug", 'Hello World', TemplateState(ChainMap(), Dataset(), MapperSpec())), 'hello-world')
        self.assertEqual(evaluate("slug", 'Hello%World', TemplateState(ChainMap(), Dataset(), MapperSpec())), 'hello_world')
        self.assertEqual(evaluate("slug", 'Hello/World', TemplateState(ChainMap(), Dataset(), MapperSpec())), 'hello_world')
        self.assertEqual(evaluate("slug", 'Hello[World]', TemplateState(ChainMap(), Dataset(), MapperSpec())), 'hello_world_')
        self.assertEqual(evaluate("slug", Literal('Hello World'), TemplateState(ChainMap(), Dataset(), MapperSpec())), 'hello-world')
        self.assertEqual(evaluate("slug", 123, TemplateState(ChainMap(), Dataset(), MapperSpec())), '123')
        self.assertRaises(ValueError, lambda: evaluate("slug", None, TemplateState(ChainMap(), Dataset(), MapperSpec())))