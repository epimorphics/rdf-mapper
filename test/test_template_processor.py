import unittest
from io import StringIO
from lib.template_processor import TemplateProcessor
from lib.mapper_spec import MapperSpec
import re
from rdflib import Literal, URIRef, XSD

class TestTemplateProcessor(unittest.TestCase):
    row1 = {"$row": 1, "$file": "file", "x": "foo", "y":"bar", "id": "123",
            "croplink" : [{"crop" : "barley", "qualifier": "winter"}],
            "label" : "label1"}
    row2 = {"$row": 2, "$file": "file", "id": "456", "label" : "label2"}
    row3 = {"$row": 3, "$file": "file", "id": "789", "label" : "label1"}

    def test_default_mapping(self):
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
            [self.row1],
            """@prefix ns1: <https://data.agrimetrics.co.uk/datasets/testds/def/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

<https://data.agrimetrics.co.uk/datasets/testds/data/registration/file-1> a <https://data.agrimetrics.co.uk/datasets/testds/def/classes/registration> ;
    ns1:id "123" .

ns1:id a rdf:Property ;
    rdfs:label "id" .

<https://data.agrimetrics.co.uk/datasets/testds/def/classes/registration> a owl:Class ;
    rdfs:label "registration" .

"""
            )

    def test_explicit_mapping(self):
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
            [self.row1],
            """@prefix ns1: <https://data.agrimetrics.co.uk/datasets/testds/def/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

<http://example.com/1> a skos:Concept ;
    ns1:p 123 .

ns1:p a rdf:Property ;
    rdfs:label "p" .

""")

    def test_inverse_prop(self):
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
            [self.row1],
            """@prefix ns1: <https://data.agrimetrics.co.uk/datasets/testds/def/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

<http://example.com/collection> skos:member <http://example.com/1> .

ns1:p a rdf:Property ;
    rdfs:label "p" .

<http://example.com/1> a skos:Concept ;
    ns1:p 123 .

""")

    def test_property_spec(self):
        self.do_test(
             MapperSpec({
                "globals": {"$datasetID": "testds"},
                "namespaces" : { "aglib" : "https://data.agrimetrics.co.uk/library/def/" },
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
            [self.row1],
            """@prefix ns1: <https://data.agrimetrics.co.uk/library/def/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

<https://data.agrimetrics.co.uk/datasets/testds/data/registration/file-1> a <https://data.agrimetrics.co.uk/datasets/testds/def/classes/registration>,
        ns1:Reg ;
    ns1:RegNo 123 .

ns1:RegNo a rdf:Property ;
    rdfs:label "regNo" ;
    rdfs:comment "identifier for registration" .

<https://data.agrimetrics.co.uk/datasets/testds/def/classes/registration> a owl:Class ;
    rdfs:label "registration" .

""")

    def test_embedded_template(self):
        self.do_test(
             MapperSpec({
                "globals": {"$datasetID": "testds"},
                "namespaces" : { "aglib" : "https://data.agrimetrics.co.uk/library/def/" },
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
            [self.row1],
            """@prefix ns1: <https://data.agrimetrics.co.uk/datasets/testds/def/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

<https://data.agrimetrics.co.uk/datasets/testds/data/registration/file-1> a <https://data.agrimetrics.co.uk/datasets/testds/def/classes/registration> ;
    ns1:crop-link <https://data.agrimetrics.co.uk/datasets/testds/data/registration/file-1/crop-situation/0> ;
    ns1:regNo "123" .

ns1:crop a rdf:Property ;
    rdfs:label "crop" .

ns1:crop-link a rdf:Property ;
    rdfs:label "crop-link" .

ns1:qualifier a rdf:Property ;
    rdfs:label "qualifier" .

ns1:regNo a rdf:Property ;
    rdfs:label "regNo" .

<https://data.agrimetrics.co.uk/datasets/testds/data/registration/file-1/crop-situation/0> a <https://data.agrimetrics.co.uk/datasets/testds/def/classes/crop-situation> ;
    ns1:crop "barley" ;
    ns1:qualifier "winter" .

<https://data.agrimetrics.co.uk/datasets/testds/def/classes/crop-situation> a owl:Class ;
    rdfs:label "crop-situation" .

<https://data.agrimetrics.co.uk/datasets/testds/def/classes/registration> a owl:Class ;
    rdfs:label "registration" .

"""
            )
            
    def test_one_off(self):
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
            [self.row1],
            """@prefix org: <http://www.w3.org/ns/org#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .

<https://data.agrimetrics.co.uk/datasets/testds/data/HSE/HSE> a org:Organization ;
    skos:prefLabel "Health and Safety Executive"@en .

""")

    def test_auto_cv(self):
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
            [self.row1, self.row2, self.row3],
            """@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix ns1: <https://data.agrimetrics.co.uk/datasets/testds/def/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .

<http://example.com/123> a <https://data.agrimetrics.co.uk/datasets/testds/def/classes/registration> ;
    ns1:prop <https://data.agrimetrics.co.uk/datasets/testds/def/scheme1/label1> .

<http://example.com/456> a <https://data.agrimetrics.co.uk/datasets/testds/def/classes/registration> ;
    ns1:prop <https://data.agrimetrics.co.uk/datasets/testds/def/scheme1/label2> .

<http://example.com/789> a <https://data.agrimetrics.co.uk/datasets/testds/def/classes/registration> ;
    ns1:prop <https://data.agrimetrics.co.uk/datasets/testds/def/scheme1/label1> .

ns1:prop a rdf:Property ;
    rdfs:label "prop" .

<https://data.agrimetrics.co.uk/datasets/testds/def/scheme1/label2> a skos:Concept ;
    skos:inScheme ns1:scheme1_scheme ;
    skos:prefLabel "label2" .

ns1:scheme1_scheme a skos:ConceptScheme ;
    dcterms:description "Automatically generated concept scheme scheme1" ;
    dcterms:title "scheme1" ;
    skos:hasTopConcept <https://data.agrimetrics.co.uk/datasets/testds/def/scheme1/label1>,
        <https://data.agrimetrics.co.uk/datasets/testds/def/scheme1/label2> .

<https://data.agrimetrics.co.uk/datasets/testds/def/classes/registration> a owl:Class ;
    rdfs:label "registration" .

<https://data.agrimetrics.co.uk/datasets/testds/def/scheme1/label1> a skos:Concept ;
    skos:inScheme ns1:scheme1_scheme ;
    skos:prefLabel "label1" .

""")

    def test_auto_cv_hash(self):
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
            [self.row1, self.row2, self.row3],
            """@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix ns1: <https://data.agrimetrics.co.uk/datasets/testds/def/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .

<http://example.com/123> a <https://data.agrimetrics.co.uk/datasets/testds/def/classes/registration> ;
    ns1:prop <https://data.agrimetrics.co.uk/datasets/testds/def/scheme1/LQOLIG61J9UEV7BN9JOF36NUSRGICPDM> .

<http://example.com/456> a <https://data.agrimetrics.co.uk/datasets/testds/def/classes/registration> ;
    ns1:prop <https://data.agrimetrics.co.uk/datasets/testds/def/scheme1/O2GA7EPQ6EREHPUGTKU7VEUD30R6LLDA> .

<http://example.com/789> a <https://data.agrimetrics.co.uk/datasets/testds/def/classes/registration> ;
    ns1:prop <https://data.agrimetrics.co.uk/datasets/testds/def/scheme1/LQOLIG61J9UEV7BN9JOF36NUSRGICPDM> .

ns1:prop a rdf:Property ;
    rdfs:label "prop" .

<https://data.agrimetrics.co.uk/datasets/testds/def/scheme1/O2GA7EPQ6EREHPUGTKU7VEUD30R6LLDA> a skos:Concept ;
    skos:inScheme ns1:scheme1_scheme ;
    skos:prefLabel "label2" .

ns1:scheme1_scheme a skos:ConceptScheme ;
    dcterms:description "Automatically generated concept scheme scheme1" ;
    dcterms:title "scheme1" ;
    skos:hasTopConcept <https://data.agrimetrics.co.uk/datasets/testds/def/scheme1/LQOLIG61J9UEV7BN9JOF36NUSRGICPDM>,
        <https://data.agrimetrics.co.uk/datasets/testds/def/scheme1/O2GA7EPQ6EREHPUGTKU7VEUD30R6LLDA> .

<https://data.agrimetrics.co.uk/datasets/testds/def/classes/registration> a owl:Class ;
    rdfs:label "registration" .

<https://data.agrimetrics.co.uk/datasets/testds/def/scheme1/LQOLIG61J9UEV7BN9JOF36NUSRGICPDM> a skos:Concept ;
    skos:inScheme ns1:scheme1_scheme ;
    skos:prefLabel "label1" .

""")
            
    def do_test(self, spec: MapperSpec, rows: list, expected: str):
        self.maxDiff = 5000
        output = StringIO("")
        proc = TemplateProcessor(spec, "test", output)
        for row in rows:
            result = proc.process_row(row).serialize(format='turtle')
        if not expected: print(result)
        self.assertEqual(expected, result)

if __name__ == '__main__':
    unittest.main()
