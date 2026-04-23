from pathlib import Path
import unittest

from rdf_mapper.lib.mapper_spec import MapperSpec, ResourceModel, ResourceSpec

class TestMapperModel(unittest.TestCase):

    def test_resource_spec_cannot_have_both_pattern_and_properties(self) -> None:
        with self.assertRaises(ValueError):
            ResourceSpec(ResourceModel(name="test", pattern="{var}", properties={"p1": "v1"}))

    def test_resource_spec_must_have_pattern_or_properties(self) -> None:
        with self.assertRaises(ValueError):
            ResourceSpec(ResourceModel(name="test"))

    def test_resource_spec_cannot_have_both_graph_and_graphAdd(self) -> None:
        with self.assertRaises(ValueError):
            config = {
                "name": "test",
                "@graph": "<http://example.com/graph>",
                "@graphAdd": "<http://example.com/graph2>"
            }
            ResourceSpec(ResourceModel(**config)) # type: ignore

class TestMapperSpec(unittest.TestCase):

    def test_property_listify(self) -> None:
        rs = ResourceSpec(
                ResourceModel(
                    name = "test",
                    properties = {
                        "p1" : "v1",
                        "p2" : "v2"
                    }
                )
            )
        self.assertEqual("test", rs.name)
        self.assertEqual([("p1", "v1"),("p2", "v2")], rs.properties)
        self.assertEqual("v2", rs.find_prop_defn("p2"))

    def test_merge_embedded_resources(self) -> None:
        ms1 = MapperSpec({
            "imports":
                [
                    "embedded.yaml"
                ],
        })
        self.assertEqual(1, len(ms1.embedded_resources))
        self.assertIn("embedded", ms1.embedded_resources)

if __name__ == '__main__':
    unittest.main()
