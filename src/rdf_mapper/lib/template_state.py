from __future__ import annotations

from collections import ChainMap
from typing import Any

from rdflib import Dataset, Graph, IdentifiedNode, URIRef

from rdf_mapper.lib.mapper_spec import MapperSpec
from rdf_mapper.lib.reconcile import MatchResult

DEFAULT_GRAPH = "urn:x-rdflib:default"

class TemplateState:
    """
    Object to carry the state information through each stage of the template processing.

    This is separated out here so we can use in both the processor and support module without import loops.
    The state gives access to:
    * the transform specification
    * the binding context with both data from this row and global context
    * backlinks giving the URIs for resources already generated for this row
    * the RDF graph being generated, this graph might span the whole transform so far or some small
      block for just this row or a batch of rows
    * a backlog of reconciliation requests to run in batches

    The context will include the following variables:
    * $baseURI     - base of URI for all data and definitions, there is a default but can be set in spec
    * $datasetID   - short id string for this dataset, must be set in spec
    * $file        - name of the file being ingested
    * $row         - row number of the line being ingested
    * $prop        - name of the current property being expanded
    * $datasetBase - base URI for this dataset by default computed from baseURI and datasetID
    * $graph       - the graph being generated, use `urn:x-rdflib:default` for the default graph
    * $resourceID  - short ID for the resource being generated, uses the name field in the template
    * $parentID    - full URI for parent resource when processing embedded templates
    * $listIndex   - index in list when processing a list of results from a chained transform
    * $reconciliationAPI - API endpoint for reconciliation, may be global or for a specific property
    """

    def __init__(self, context: ChainMap[str,Any], dataset: Dataset, spec: MapperSpec,
                 preserved_graphs: set[str] = set(), reconcile_stack: dict = {}) -> None:
        self.spec = spec
        self.context = context
        self.dataset = dataset
        self.backlinks = {}
        self.preserved_graphs = preserved_graphs
        self.reconcile_stack = reconcile_stack
        self.ensure_graph()

    def add_to_context(self, prop: str, value: str) -> None:
        self.context[prop] = value

    def get(self, prop: str) -> str | None:
        return self.context.get(prop)

    def child(self, subcontext: dict) -> TemplateState:
        """Return a new template state which mirrors this but with additional temporary context bindings."""
        child = TemplateState(self.context.new_child(subcontext), self.dataset, self.spec,
                              self.preserved_graphs, self.reconcile_stack)
        child.backlinks = self.backlinks
        return child

    def record_reconcile_request(self, record: ReconciliationRecord) -> None:
        """Record a reconciliation request, which might or might not have already been attempted and succeeded."""
        self.reconcile_stack[record.lookup_key()] = record

    def reconciled_ref(self, key: str, keytype: str | None) -> URIRef | None:
        """Return the URI for a reconciliation result or proxy if we have created one"""
        record =  self.reconcile_stack.get(f"{key}-{keytype}")
        return record.id if record else None

    def record_auto_cv(self, name: str, label: str, _id: IdentifiedNode) -> None:
        """Record an auto generated CV entry.

           We reuse the backlinks dict since cv names and backlink names will be distinct.
        """
        self.backlinks[f"{name}/{label}"] = _id

    def record_auto_emit(self, _type: str, label: str) -> bool:
        """Record an auto emitted property/class spec. Return true if already known.

           We reuse the backlinks dict since cv names and backlink names will be distinct.
        """
        key = f"{_type}#{label}"
        if key in self.backlinks:
            return True
        else:
            self.backlinks[key] = True
            return False

    def get_auto_entry(self, name: str, label: str) -> URIRef | None:
        """If there is an auto CV entry for this already return it."""
        return self.backlinks.get(f"{name}/{label}")

    def ensure_graph(self) -> None:
        """If no graph is set then make it the default graph"""
        if '$graph' not in self.context:
            self.context['$graph'] = DEFAULT_GRAPH

    def switch_to_graph(self, graph: str, preserve: bool) -> TemplateState:
        """Switch to a named graph, returns new temporary state."""
        if preserve:
            self.preserved_graphs.add(graph)
        return self.child({'$graph': graph})

    def current_graph(self) -> Graph:
        """Return the current graph being generated."""
        return self.dataset.graph(self.context['$graph'])

    def add_to_graph(self, triple: tuple) -> None:
        """Add a triple to the current graph."""
        self.current_graph().add(triple)

class ReconciliationRecord:
    def __init__(self, key: str, keytype: str | None, _id: IdentifiedNode | None = None) -> None:
        self._id = _id
        self.key = key
        self.keytype = keytype
        self.result: MatchResult | None = None

    def lookup_key(self) -> str:
        return f"{self.key}-{self.keytype}"

    def id(self) -> IdentifiedNode | None:
        if self._id:
            return self._id
        elif self.result and self.result.match:
            return URIRef(self.result.match.id)
        else:
            return None
