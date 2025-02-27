import re
import unittest

from rdflib import XSD, Graph, Literal, URIRef

from rdf_mapper.lib.mapper_spec import MapperSpec
from rdf_mapper.lib.template_state import TemplateState
from rdf_mapper.lib.template_support import (
    asBoolean,
    asDate,
    asDateOrDatetime,
    asDateTime,
    pattern_expand,
    uri_expand,
    value_expand,
)


class TestTemplateSupport(unittest.TestCase):

    def test_var_expand(self) -> None:
        context = {"a": "aval", "b": 42, "z": "zval"}
        self.assertEqual(pattern_expand("foo {a} bar", context), "foo aval bar")
        self.assertEqual(pattern_expand("{a}foo{b}bar{z}", context), "avalfoo42barzval")

    def test_function_expand(self) -> None:
        context = {"x": 5}
        self.assertEqual(pattern_expand("{x | asInt3}", context), 15)
        self.assertEqual(pattern_expand("foo {x | asInt3} bar", context), "foo 15 bar")

    def test_uri_expand(self) -> None:
        spec = MapperSpec({"globals": {"$datasetID": "testds"}})
        context = spec.context.new_child({
            "$row": 3, "$file": "file",
            "x": "foo", "y":"bar",
            "$resourceID":"resty",
            })
        state = TemplateState(context, Graph(), spec)
        self.assertEqual(
            uri_expand("p", spec.namespaces, state),
            "https://epimorphics.com/datasets/testds/def/p")
        self.assertEqual(
            uri_expand("<row>", spec.namespaces, state),
            "https://epimorphics.com/datasets/testds/data/resty/file-3")
        self.assertTrue(re.fullmatch(
            r"https://epimorphics.com/datasets/testds/data/resty/[a-z0-9\-]*",
            str(uri_expand("<uuid>", spec.namespaces, state))))
        self.assertEqual(
            uri_expand("<http://example.com/{x}>", spec.namespaces, state),
            "http://example.com/foo")
        self.assertEqual(
            uri_expand("<skos:{x}>", spec.namespaces, state),
            "http://www.w3.org/2004/02/skos/core#foo")
        self.assertEqual(
            uri_expand("<hash(x, y)>", spec.namespaces, state),
            "https://epimorphics.com/datasets/testds/data/resty/H11TFU942OGHRQFBN5HVUJ72G4IP6A3O")

    def test_value_expand(self) -> None:
        spec = MapperSpec({"globals": {"$datasetID": "testds"}})
        state = TemplateState(spec.context.new_child({
            "$row": 3, "$file": "file",
            "x": "foo", "y":"bar",
            "l" : "en",
            "d" : "1.23",
            "list" : "foo, bar"
        }))

        self.assertEqual(
            value_expand("hell{x}o", spec.namespaces, state),
            Literal("hellfooo"))
        self.assertEqual(
            value_expand("{x}{y}@{l}", spec.namespaces, state),
            Literal("foobar", lang="en"))
        self.assertEqual(
            value_expand("{d}", spec.namespaces, state),
            Literal("1.23"))
        self.assertEqual(
            value_expand("{d | asDecimal}", spec.namespaces, state),
            Literal("1.23", datatype=XSD.decimal))
        self.assertEqual(
            value_expand("<skos:Concept>", spec.namespaces, state),
            URIRef("http://www.w3.org/2004/02/skos/core#Concept"))
        self.assertEqual(
            value_expand("{list | splitComma}", spec.namespaces, state),
            [Literal("foo"), Literal("bar")])

    def test_dates(self) -> None:
        self.assertEqual(asDate("2023-05-18"), Literal("2023-05-18", datatype=XSD.date))
        self.assertEqual(asDate("18 May 2023"), Literal("2023-05-18", datatype=XSD.date))
        self.assertEqual(asDate("2023-05-18 12:34"), Literal("2023-05-18", datatype=XSD.date))
        self.assertEqual(asDateTime("2023-05-18 12:34"), Literal("2023-05-18T12:34:00", datatype=XSD.dateTime))
        self.assertEqual(asDateTime("18 May 2023 12:34"), Literal("2023-05-18T12:34:00", datatype=XSD.dateTime))
        self.assertEqual(asDateOrDatetime("18 May 2023 12:34"), Literal("2023-05-18T12:34:00", datatype=XSD.dateTime))
        self.assertEqual(asDateOrDatetime("18 May 2023"), Literal("2023-05-18", datatype=XSD.date))
        self.assertEqual(asDateOrDatetime("2023"), Literal("2023-01-01", datatype=XSD.date))

    def test_boolean(self) -> None:
        self.assertEqual(asBoolean("true"), Literal(True, datatype=XSD.boolean))
        self.assertEqual(asBoolean("True"), Literal(True, datatype=XSD.boolean))
        self.assertEqual(asBoolean("Yes"), Literal(True, datatype=XSD.boolean))
        self.assertEqual(asBoolean("1"), Literal(True, datatype=XSD.boolean))
        self.assertEqual(asBoolean("no"), Literal(False, datatype=XSD.boolean))
        self.assertEqual(asBoolean("false"), Literal(False, datatype=XSD.boolean))
        self.assertEqual(asBoolean("0"), Literal(False, datatype=XSD.boolean))

    def test_fn_call(self) -> None:
        spec = MapperSpec({"globals": {"$datasetID": "testds"}})
        state = TemplateState(spec.context.new_child({
            "$row": 3, "$file": "file", "x": "foo-bar-baz"
        }))
        self.assertEqual(
            value_expand("{x | split('-')}", spec.namespaces, state),
            list([Literal("foo"), Literal("bar"), Literal("baz")]))

    def test_now(self) -> None:
        spec = MapperSpec({"globals": {"$datasetID": "testds"}})
        state = TemplateState(spec.context.new_child({"$row": 1, "$file": "file"}))
        v = value_expand("{|now}", spec.namespaces, state)
        self.assertTrue(isinstance(v, Literal))
        self.assertEqual(v.datatype, XSD.dateTime)

if __name__ == '__main__':
    unittest.main()
