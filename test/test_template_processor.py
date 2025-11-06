import unittest
from io import StringIO

from rdf_mapper.lib.mapper_spec import MapperSpec
from rdf_mapper.lib.template_processor import DEFAULT_GRAPH, TemplateProcessor


class TestTemplateProcessor(unittest.TestCase):
    row1 = {"$row": 1, "$file": "file", "x": "foo", "y":"bar", "id": "123",
            "croplink" : [{"crop" : "barley", "qualifier": "winter"}],
            "label" : "label1"}
    row2 = {"$row": 2, "$file": "file", "id": "456", "label" : "label2"}
    row3 = {"$row": 3, "$file": "file", "id": "789", "label" : "label1"}
    row4 = {"$row": 4, "$file": "file", "id": "444", "flag" : "n"}

    def test_default_mapping(self) -> None:
        self.do_test(
             MapperSpec({
                "globals": {"$datasetID": "testds"},
                "resources" : [{
                    "name": "registration",
                    "properties": [
                        {"id" : ""}
                    ]
                }]
            }),
            [self.row1], "default_mapping.ttl")

    def test_default_mapping_no_auto_declare(self) -> None:
        self.do_test(
             MapperSpec({
                "globals": {"$datasetID": "testds"},
                "resources" : [{
                    "name": "registration",
                    "properties": [
                        {"id" : ""}
                    ]
                }]
            }, auto_declare=False),
            [self.row1], "default_mapping_no_auto_declare.ttl")

    def test_explicit_mapping(self) -> None:
        self.do_test(
             MapperSpec({
                "globals": {"$datasetID": "testds"},
                "resources" : [{
                    "name": "registration",
                    "properties": {
                        "@id" : "<http://example.com/{$row}>",
                        "@type" : "<skos:Concept>",
                        "p" : "{id | asInt}"
                    }
                }]
            }),
            [self.row1], "explicit_mapping.ttl")

    def test_skip_missing(self) -> None:
        self.do_test(
             MapperSpec({
                "globals": {"$datasetID": "testds"},
                "namespaces" : { "def" : "https://epimorphics.com/library/def/" },
                "resources" : [{
                    "name": "registration",
                    "properties": {
                        "@id" : "<http://example.com/{$row}>",
                        "@type" : "<skos:Concept>",
                        "<def:p>" : "{id | asInt}",
                        "<def:missing>" : "{missing}",
                        "<def:missing2>" : "{missing}@en"
                    }
                }]
            }),
            [self.row1], "skip_missing.ttl")

    def test_skip_missing_in_list(self) -> None:
        self.do_test(
             MapperSpec({
                "globals": {"$datasetID": "testds"},
                "namespaces" : { "def" : "https://epimorphics.com/library/def/" },
                "resources" : [{
                    "name": "registration",
                    "properties": {
                        "@id" : "<http://example.com/{$row}>",
                        "@type" : "<skos:Concept>",
                        "<def:missing>" : ["{missing}", "{id}"]
                    }
                }]
            }),
            [self.row1], "skip_missing_in_list.ttl")

    def test_inverse_prop(self) -> None:
        self.do_test(
             MapperSpec({
                "globals": {"$datasetID": "testds"},
                "resources" : [{
                    "name": "registration",
                    "properties": {
                        "@id" : "<http://example.com/{$row}>",
                        "@type" : "<skos:Concept>",
                        "p" : "{id | asInt}",
                        "^<skos:member>" : "<http://example.com/collection>"
                    }
                }]
            }),
            [self.row1], "inverse_prop.ttl")

    def test_property_spec(self) -> None:
        self.do_test(
             MapperSpec({
                "globals": {"$datasetID": "testds"},
                "namespaces" : { "aglib" : "https://epimorphics.com/library/def/" },
                "properties" : [{
                    "name" : "regNo",
                    "comment" : "identifier for registration",
                    "prop" : "<aglib:RegNo>",
                    "class": "<aglib:Reg>",
                    "type" : "Int"
                }],
                "resources" : [{
                    "name": "registration",
                    "properties": {
                        ":regNo" : "{id}"
                    }
                }]
            }),
            [self.row1],"property_spec.ttl")

    def test_embedded_template(self) -> None:
        self.do_test(
             MapperSpec({
                "globals": {"$datasetID": "testds"},
                "namespaces" : { "aglib" : "https://epimorphics.com/library/def/" },
                "resources" : [{
                    "name": "registration",
                    "properties": {
                        "regNo" : "{id}",
                        "crop-link" : "{croplink | map_to('crop-situation')}"
                    }
                }],
                "embedded" : [{
                    "name": "crop-situation",
                    "properties" : {
                        "@id"  : "<parent>",
                        "crop" : "{crop}",
                        "qualifier" : "{qualifier}"
                    }
                }]
            }),
            [self.row1], "embedded_template.ttl")

    def test_one_off(self) -> None:
        self.do_test(
             MapperSpec({
                "globals": {"$datasetID": "testds"},
                "one_offs" : [{
                    "name" : "HSE",
                    "properties" : {
                    "@id" : "<HSE>",
                    "@type" : "<org:Organization>",
                    "<skos:prefLabel>" : "Health and Safety Executive@en"
                    }
                }]
            }),
            [self.row1], "one_off.ttl")

    def test_auto_cv(self) -> None:
        self.do_test(
            MapperSpec({
                "globals": {"$datasetID": "testds"},
                "resources" : [{
                    "name": "registration",
                    "properties": {
                        "@id" : "<http://example.com/{id}>",
                        "prop" : "{label | autoCV('scheme1','label')}"
                    }
                }]
            }),
            [self.row1, self.row2, self.row3], "auto_cv.ttl")

    def test_auto_cv_hash(self) -> None:
        self.do_test(
            MapperSpec({
                "globals": {"$datasetID": "testds"},
                "resources" : [{
                    "name": "registration",
                    "properties": {
                        "@id" : "<http://example.com/{id}>",
                        "prop" : "{label | autoCV('scheme1','hash')}"
                    }
                }]
            }),
            [self.row1, self.row2, self.row3], "auto_cv_hash.ttl")

    def test_property_value_list(self) -> None:
        self.do_test(
            MapperSpec({
                "globals": {"$datasetID": "testds"},
                "resources": [{
                    "name": "registration",
                    "properties": {
                        "@id":"<http://example.com/{id}>",
                        "prop": [
                            "<http://example.com/value/{x}>",
                            "{y}"
                        ]
                    }
                }]
            }),
            [self.row1], "property_value_list.ttl")

    def test_nested_resource_spec(self) -> None:
        self.do_test(
            MapperSpec({
                "globals": {"$datasetID": "testds"},
                "resources": [{
                    "name": "registration",
                    "properties": {
                        "@id": "<http://example.com/{id}>",
                        "prop": {
                            "name": "nested",
                            "properties": {
                                "@id": "<_>",
                                "val": "{x}"
                            }
                        }
                    }
                }]
            }),
            [self.row1], "nested_resource_spec.ttl")

    def test_map_by(self) -> None:
        self.do_test(
            MapperSpec({
                "mappings" : {
                    "testmap" : {
                        "foo" : "<http://example.com/Foo>",
                        "bar" : "<http://example.com/Bar>",
                        "baz" : "<http://example.com/Baz>"
                    }
                },
                "resources": [{
                    "name": "registration",
                    "properties": {
                        "@id": "<http://example.com/{id}>",
                        "p": "{x | map_by('testmap')}",
                        "q": "{y | map_by('testmap')}"
                    }
                }]
            }, auto_declare=False),
            [self.row1], "map_by.ttl" )

    def test_required_filter(self) -> None:
        self.do_test(
            MapperSpec({
                "resources": [{
                    "name": "Test",
                    "requires": { "id": "123" },
                    "properties": {
                        "@id" : "<http://example.com/{id}>",
                        "@type" : "<http://example.com/File>",
                    }
                }]
            }, auto_declare=False),
            [self.row1, self.row2], "required_filter.ttl"
        )

    def test_required_in_filter(self) -> None:
        self.do_test(
        MapperSpec({
            "resources": [{
                "name": "Test",
                "requires": {"id": ["123", "789"]},
                "properties": {
                    "@id": "<http://example.com/{id}>",
                    "@type": "<http://example.com/File>",
                }
            }]
        }, auto_declare=False),
        [self.row1, self.row2],
        "required_filter.ttl"
        )

    def test_unless_filter(self) -> None:
        self.do_test(
            MapperSpec({
                "resources": [{
                    "name": "Test",
                    "unless": { "id": "123" },
                    "properties": {
                        "@id" : "<http://example.com/{id}>",
                        "@type" : "<http://example.com/File>",
                    }
                }]
            }, auto_declare=False),
            [self.row1, self.row2], "unless_filter.ttl"
        )

    def test_unless_none_filter(self) -> None:
        self.do_test(
            MapperSpec({
                "resources": [{
                    "name": "Test",
                    "unless": { "x": None },
                    "properties": {
                        "@id" : "<http://example.com/{id}>",
                        "@type" : "<http://example.com/File>",
                    }
                }]
            }, auto_declare=False),
            [
                self.row1,
                self.row2,
                {"$row": 3, "$file": "file", "id": "789", "x": "", "label": "label1"}
            ],
            "unless_none_filter.ttl"
        )

    def test_required_none_filter(self) -> None:
        self.do_test(
            MapperSpec({
                "resources": [{
                    "name": "Test",
                    "requires": { "x": None },
                    "properties": {
                        "@id" : "<http://example.com/{id}>",
                        "@type" : "<http://example.com/File>",
                    }
                }]
            }, auto_declare=False),
            [self.row1, self.row2], "required_filter.ttl"
        )

    def test_unless_in_filter(self) -> None:
        self.do_test(
            MapperSpec({
                "resources": [{
                    "name": "Test",
                    "unless": { "id": ["123", "789"]},
                    "properties": {
                        "@id" : "<http://example.com/{id}>",
                        "@type" : "<http://example.com/File>",
                    }
                }]
            }, auto_declare=False),
            [self.row1, self.row2, self.row3], "unless_filter.ttl"
        )

    def test_asBoolean_producing_false(self):
        self.do_test(
            MapperSpec({
                "resources": [{
                    "name": "Test",
                    "properties": {
                        "@id": "<http://example.com/{id}>",
                        "p": "{flag|asBoolean('y')}"
                    }
                }]
            }, auto_declare=False),
            [{"id": "123", "flag": "n"},{"id": "456", "flag": "y"}],
            "asBoolean_producing_false.ttl"
        )

    def do_test(self, spec: MapperSpec, rows: list, expected: str | None) -> None:
        self.maxDiff = 5000
        output = StringIO("")
        proc = TemplateProcessor(spec, "test", output, abort_on_error=False)
        for row in rows:
            proc.process_row(row)
        proc.bind_namespaces()
        result = proc.dataset.graph(DEFAULT_GRAPH).serialize(format='turtle')
        if not expected:
            print(result)
        else:
            self.assertEqual(load_expected(expected), result)

    def test_abort_on_error(self) -> None:
        spec = MapperSpec({
            "resources": [{
                "name": "Test",
                "properties": {
                    "@id": "<http://example.com/{id}>",
                    "p": "{label|asInt}"
                }
            }]
        }, auto_declare=False)
        output = StringIO("")
        proc = TemplateProcessor(spec, "test", output, abort_on_error=True)
        for row in [self.row2, self.row3]:
            proc.process_row(row)
        self.assertEqual(proc.error_count, 2)
        self.assertEqual(proc.row, 2)
        self.assertEqual(len(output.getvalue()), 0)  # No output written due to abort on error

def load_expected(name: str) -> str:
    with open(f"test/expected/{name}", 'r', encoding='utf-8') as file:
        return file.read()

if __name__ == '__main__':
    unittest.main()
