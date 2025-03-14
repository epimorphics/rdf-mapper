import os
import tempfile
from io import StringIO

from rdflib import Dataset, Literal, URIRef

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
            "@graphAdd": "<http://example.com/current>",
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

    def _init_test_dataset(self) -> Dataset:
        ds = Dataset()
        base = ds.graph(URIRef("http://example.com/base"))
        base.add((
            URIRef("http://example.com/should_go"),
            URIRef("http://example.com/p"),
            Literal(42)
        ))
        current = ds.graph(URIRef("http://example.com/current"))
        current.add((
            URIRef("http://example.com/should_stay"),
            URIRef("http://example.com/p"),
            Literal("foo")
        ))
        return ds

    def _generate_update(self, format: str) -> str:
        proc = self.run_test()
        with tempfile.TemporaryDirectory() as tmpdirname:
            filename = f"{tmpdirname}/{format}.ru"
            proc.output = open(filename, "w")
            if format == 'delete':
                proc.write_as_delete()
            else:
                proc.write_as_update()
            with open(filename, "r") as result_file:
                return result_file.read()

    def test_update(self) -> None:
            update = self._generate_update("update")
            delete = self._generate_update("delete")
            ds = self._init_test_dataset()
            ds.update(update)
            expected = sorted(self.load_expected_quads("graphs-update.trig"))
            assert expected == sorted(list(ds.quads()))

            ds.update(delete)
            expected = sorted(self.load_expected_quads("graphs-delete.trig"))
            assert expected == sorted(list(ds.quads()))
