import unittest
from collections import ChainMap

from rdflib import Dataset, Literal

from rdf_mapper.lib.mapper_spec import MapperModel, MapperSpec
from rdf_mapper.lib.pattern import Pattern
from rdf_mapper.lib.template_state import TemplateState


class TestPattern (unittest.TestCase):

    def test_langstring(self) -> None:
        pattern = Pattern("Hello@en")
        # self.assertEqual(pattern.type, "langstring")
        # self.assertEqual(pattern.lang, "en")
        # self.assertEqual(pattern.datatype, None)
        self.assertEqual(list(pattern.execute(TemplateState(ChainMap(), Dataset(), MapperSpec()))), [Literal("Hello", lang="en")])

    def test_datatype(self) -> None:
        pattern = Pattern("42^^<http://www.w3.org/2001/XMLSchema#integer>")
        self.assertEqual(list(pattern.execute(TemplateState(ChainMap(), Dataset(), MapperSpec()))), [Literal("42", datatype="http://www.w3.org/2001/XMLSchema#integer")])

    def test_simple_variable(self) -> None:
        pattern = Pattern("{name}")
        self.assertEqual(len(pattern._call_chain), 1)  # variable "name"
        self.assertTrue(callable(pattern._call_chain[0]))  # variable "name"
        state = TemplateState(
            ChainMap({"name": "Alice"}), Dataset(), MapperSpec())
        self.assertEqual(list(pattern.execute(state)), [Literal("Alice")])
        state = TemplateState(
            ChainMap({"name": ["Alice", "Bob", "Charlie"]}), Dataset(), MapperSpec())
        self.assertEqual(list(pattern.execute(state)), [Literal("Alice"), Literal("Bob"), Literal("Charlie")])
        state = TemplateState(
            ChainMap({}), Dataset(), MapperSpec())
        self.assertEqual(list(pattern.execute(state)), [])  # Missing variable should not be yielded as literals
        state = TemplateState(
            ChainMap({"name": None}), Dataset(), MapperSpec())
        self.assertEqual(list(pattern.execute(state)), [])  # None values should not be yielded as literals
        state = TemplateState(
            ChainMap({"name": ""}), Dataset(), MapperSpec())
        self.assertEqual(list(pattern.execute(state)), [])  # Empty string values should not be yielded as literals

    def test_variables_and_statics(self) -> None:
        pattern = Pattern("Hello {name}!")
        self.assertEqual(len(pattern._call_chain), 3)  # static "Hello ", variable "name", static "!"
        self.assertTrue(callable(pattern._call_chain[0]))  # static "Hello "
        self.assertTrue(callable(pattern._call_chain[1]))  # variable "name"
        self.assertTrue(callable(pattern._call_chain[2]))  # static "!"
        state = TemplateState(
            ChainMap({"name": "Alice"}), Dataset(), MapperSpec())
        self.assertEqual(list(pattern.execute(state)), [Literal("Hello Alice!")])
        state = TemplateState(
            ChainMap({}), Dataset(), MapperSpec())
        self.assertEqual(list(pattern.execute(state)), [])  # Missing variable should not be yielded as literals
        state = TemplateState(
            ChainMap({"name": None}), Dataset(), MapperSpec())
        self.assertEqual(list(pattern.execute(state)), [])  # None values should not be yielded as literals
        state = TemplateState(
            ChainMap({"name": ""}), Dataset(), MapperSpec())
        self.assertEqual(list(pattern.execute(state)), [])  # Empty string values should not be yielded as literals
        state = TemplateState(
            ChainMap({"name": ["Alice", "Bob", "Charlie"]}), Dataset(), MapperSpec())
        self.assertEqual(list(pattern.execute(state)),
                         [Literal("Hello Alice!"), Literal("Hello Bob!"), Literal("Hello Charlie!")])
        state = TemplateState(
            ChainMap({"name": ["Alice", "", "Charlie"]}), Dataset(), MapperSpec())
        self.assertEqual(list(pattern.execute(state)), [Literal("Hello Alice!"), Literal("Hello Charlie!")])

    def test_datatype_as_variable(self) -> None:
        pattern = Pattern("{@value}^^<{@type}>")
        # self.assertEqual(pattern.type, "datatype")
        state = TemplateState(
            ChainMap({"@value": "42", "@type": "http://www.w3.org/2001/XMLSchema#integer"}), Dataset(), MapperSpec())
        actual = list(pattern.execute(state))
        print(actual)
        self.assertEqual(actual, [Literal("42", datatype="http://www.w3.org/2001/XMLSchema#integer")])

    def test_variable_function_chain(self) -> None:
        pattern = Pattern("{greeting} {name | toUpper}!")
        self.assertEqual(len(pattern._call_chain), 4)  # variable "greeting", static " ", variable "name", static "!"
        state = TemplateState(
            ChainMap({"greeting": "Hi", "name": "Bob"}), Dataset(), MapperSpec())
        self.assertEqual(list(pattern.execute(state)), [Literal("Hi BOB!")])

    def test_function_chain_with_split(self) -> None:
        pattern = Pattern("{names | splitComma | toUpper}")
        state = TemplateState(
            ChainMap({"names": "Alice,Bob,Charlie"}), Dataset(), MapperSpec())
        self.assertEqual(list(pattern.execute(state)), [Literal("ALICE"), Literal("BOB"), Literal("CHARLIE")])

    def test_wrap_literal_empty_with_lang(self) -> None:
        pattern = Pattern("{greeting}@en")
        state = TemplateState(
            ChainMap({"greeting": ""}), Dataset(), MapperSpec())
        self.assertEqual(list(pattern.execute(state)), [])

    def test_wrap_literal_empty_with_datatype(self) -> None:
        pattern = Pattern("{value}^^<http://www.w3.org/2001/XMLSchema#string>")
        state = TemplateState(
            ChainMap({"value": ""}), Dataset(), MapperSpec())
        self.assertEqual(list(pattern.execute(state)), [])

    def test_wrap_literal_with_curie_datatype(self) -> None:
        pattern = Pattern("{value}^^<xsd:string>")
        state = TemplateState(
            ChainMap({"value": "test"}), Dataset(), MapperSpec(MapperModel(namespaces={"xsd": "http://www.w3.org/2001/XMLSchema#"})))
        self.assertEqual(list(pattern.execute(state)), [Literal("test", datatype="http://www.w3.org/2001/XMLSchema#string")])
