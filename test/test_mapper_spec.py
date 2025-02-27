import unittest

from rdf_mapper.lib.mapper_spec import ResourceSpec


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


if __name__ == '__main__':
    unittest.main()
