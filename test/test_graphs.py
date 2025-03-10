import os
import tempfile
from io import StringIO

from rdflib import Dataset

from rdf_mapper.lib.mapper_spec import MapperSpec
from rdf_mapper.lib.template_processor import TemplateProcessor


class TestGraphs:

    mapper_spec = {
        "namespaces" : {
            "ex" : "http://example.com/"
        },
        "resources": [{
            "name": "Base",
            "@graph": "<http://example.com/base>",
            "properties": {
                "@id": "<http://example.com/{id}>",
                "<rdfs:label>": "{label}",
                "<ex:value>": "{value}"
            }
        },{
            "name": "Current",
            "@graph": "<http://example.com/current>",
            "properties": {
                "@id": "<http://example.com/{id}>",
                "<ex:latest_value>": "{value}"
            }
        }]
    }

    rows = [
        {"$row": 1, "$file": "file", "id": "12", "label" : "label1", "value": 42},
        {"$row": 2, "$file": "file", "id": "34", "label" : "label2", "value": 35},
        {"$row": 3, "$file": "file", "id": "56", "label" : "label3", "value": 451},
    ]

    def run_test(self) -> TemplateProcessor:
        output = StringIO("")
        proc = TemplateProcessor(MapperSpec(self.mapper_spec, auto_declare=False), "test", output)
        for row in self.rows:
            proc.process_row(row)
        return proc

    def load_expected_quads(self, name: str) -> list:
        ds = Dataset()
        ds.parse(f"{os.getcwd()}/test/expected/{name}")
        return list(ds.quads())

    def load_expected_str(self, name: str) -> str:
        with open(f"test/expected/{name}", 'r', encoding='utf-8') as file:
            return file.read()

    def test_basic_graphs(self) -> None:
        actual = list(self.run_test().dataset.quads())
        assert sorted(self.load_expected_quads("graphs.trig")) == sorted(actual)

    def test_update_serialization(self) -> None:
        proc = self.run_test()
        with tempfile.TemporaryDirectory() as tmpdirname:
            filename = f"{tmpdirname}/test.ru"
            proc.output = open(filename, "w")
            proc.write_as_update()
            with open(filename, "r") as result_file:
                update = result_file.read()
                ds = Dataset()
                ds.update(update)
                assert sorted(self.load_expected_quads("graphs.trig")) == sorted(list(ds.quads()))

