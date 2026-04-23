"""
    Support for reconciliation use the OpenRefine style reconciliation API.
"""

import json
from typing import Any, cast

import requests
from rdflib import XSD, BNode, Graph, IdentifiedNode, Literal, URIRef


class ReconcileRequest:
    """Request should have text query, option type (uri string) and optional filters.

       Filters are pairs (property uri string, filter value).
       We don't use a dict because embedding dict literals in the patterns
       would mean using a real parser instead of regexs."""
    def __init__(self, query: str, type: str|None = None, filters: list[tuple] = []) -> None:  # noqa: A002
        self.query = query
        self.type = type
        self.filters = filters

def requestReconcile(endpoint: str, terms: list[ReconcileRequest]) -> list:
    """Request a batch of reconciliations."""
    batch  = {}
    for i, term in enumerate(terms):
        q: dict[str, str|list[str]] = {"query" : term.query}
        if term.type:
            q["type"] = term.type
        if term.filters:
            filters = []
            for prop, val in term.filters:
                filters.append({"pid" : prop, "v": val})
            q["properties"] = filters
        batch[str(i)] = q
    query={"queries" : json.dumps(batch)}
    response = requests.post(endpoint, data=query)
    if response.status_code != 200:
        raise ValueError(f"Failure using reconciliation service {response.status_code} {response.content}")
    results: list[MatchResult|None] = [None] * len(terms)
    for key, match in response.json().items():
        results[int(key)] = MatchResult(match.get("result"))
    return results

RECONCILIATION_VOCAB = "http://epimorphics.net/vocabs/reconciliation/"
REC_POSSIBLE_MATCH = URIRef(RECONCILIATION_VOCAB + "possibleMatch")
REC_SCORE = URIRef(RECONCILIATION_VOCAB + "score")
REC_MATCH = URIRef(RECONCILIATION_VOCAB + "match")
REC_LABEL = URIRef(RECONCILIATION_VOCAB + "label")

class MatchEntry:
    def __init__(self, result: dict[str, Any]) -> None:
        self.id = cast(str, result.get("id"))
        self.name = result.get("name")
        self.score = result.get("score")
        self.matched = result.get("match")

    def __str__(self) -> str:
        return f"{self.name} matched at {self.score}"

    def record_as_rdf(self, g: Graph, proxy: IdentifiedNode) -> None:
        node = BNode()
        g.add((node, REC_SCORE, Literal(self.score, datatype=XSD.decimal)))
        g.add((node, REC_MATCH, URIRef(self.id)))
        g.add((node, REC_LABEL, Literal(self.name)))
        g.add((proxy, REC_POSSIBLE_MATCH, node))

class MatchResult:
    def __init__(self, results: list) -> None:
        possible_matches = [MatchEntry(entry) for entry in results]
        if len(possible_matches) == 1 and possible_matches[0].matched:
            self.match = possible_matches[0]
        else:
            self.match = None
            self.possible_matches = possible_matches

    def __str__(self) -> str:
        if self.match:
            return f"matched {self.match.name} = {self.match.id}"
        elif len(self.possible_matches) > 0:
            return f"possible matches {[str(m) for m in self.possible_matches]}"
        else:
            return  "no match"


if __name__ == "__main__":
    # Temp testing
#    req = ReconcileRequest("glyphosate", "https://data.agrimetrics.co.uk/def/AgriSubstance")
    req = ReconcileRequest("glyphosate", None, [("http://www.w3.org/2004/02/skos/core#inScheme", "https://data.agrimetrics.co.uk/agri_substances/AgriSubstances")])
    result = requestReconcile("http://localhost:8888/rd/api/reconcile", [req])
    print(result[0])
