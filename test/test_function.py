
from typing_extensions import ChainMap
import unittest

from rdflib import Dataset, Literal
from rdf_mapper.lib.function import register, get, evaluate
from rdf_mapper.lib.mapper_spec import MapperSpec
from rdf_mapper.lib.template_state import TemplateState


class TestFunctionRegistry(unittest.TestCase):
    def test_register_and_get(self):
        def test_func(value, state, arg1):
            return Literal(f"{value} {arg1}")
        register("test_func", test_func)
        fn = get("test_func")
        self.assertEqual(fn(Literal("Hello"), TemplateState(ChainMap(), Dataset(), MapperSpec()), "World"), Literal("Hello World"))
    
    def test_get_with_args(self):
        def test_func(value, state, arg1):
            return Literal(f"{value} {arg1}")
        register("test_func", test_func)
        result = evaluate("test_func('World')", Literal("Hello"), TemplateState(ChainMap(), Dataset(), MapperSpec()))
        self.assertEqual(result, Literal("Hello World"))
    
    def test_get_with_variable_arg(self):
        def test_func(value, state, arg1):
            return Literal(f"{value} {arg1}")
        register("test_func", test_func)
        result = evaluate("test_func(greeting)", Literal("Hello"), TemplateState(ChainMap({"greeting": "Hi"}), Dataset(), MapperSpec()))
        self.assertEqual(result, Literal("Hello Hi"))
    
    def test_eval_with_global_function_no_params(self):
        result = evaluate("asInt3", '5', TemplateState(ChainMap(), Dataset(), MapperSpec()))
        self.assertEqual(result, 15)
    
    def test_eval_with_global_function_with_string_param(self):
        result = evaluate("split(',|:')", 'a,b:c', TemplateState(ChainMap(), Dataset(), MapperSpec()))
        self.assertEqual(result, ['a', 'b', 'c'])
    
    def test_eval_with_global_function_with_variable_param(self):
        result = evaluate("split(delimiter)", 'a,b:c', TemplateState(ChainMap({"delimiter": ",|:"}), Dataset(), MapperSpec()))
        self.assertEqual(result, ['a', 'b', 'c'])

