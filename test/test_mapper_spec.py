from pathlib import Path
import unittest

from rdf_mapper.lib.mapper_spec import MapperSpec, ResourceSpec


class TestMapperSpec(unittest.TestCase):

    def test_property_listify(self) -> None:
        rs = ResourceSpec({
            "name" : "test",
            "properties": {
                "p1" : "v1",
                "p2" : "v2"
            }
        })
        self.assertEqual("test", rs.name)
        self.assertEqual([("p1", "v1"),("p2", "v2")], rs.properties)
        self.assertEqual("v2", rs.find_prop_defn("p2"))

    def test_merge_embedded_resources(self) -> None:
        template_path = Path(__file__).parent / "templates" / "embedded.yaml"
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
