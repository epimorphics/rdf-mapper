"""
Processor to generate RDF transformed output from each row of source data based on mapper spec.
"""

import logging
from typing import TextIO

from rdflib import Dataset, Graph, URIRef
from rdflib.namespace import NamespaceManager

from rdf_mapper.lib.mapper_spec import MapperSpec
from rdf_mapper.lib.template_state import TemplateState
from rdf_mapper.lib.template_support import process_resource_spec

DEFAULT_GRAPH = "urn:x-rdflib:default"
DEFAULT_GRAPH_ID = URIRef(DEFAULT_GRAPH)

class TemplateProcessor:
    def __init__(self, spec: MapperSpec, filename: str, output: TextIO, abort_on_error: bool = False) -> None:
        self.spec = spec
        self.output = output
        self.dataset = Dataset()  # TODO streaming version
        self.bind_namespaces()
        self.row = 0
        self.abort_on_error = abort_on_error
        self.error_count = 0
        self.context = self.spec.context.new_child({"$file": filename, "$row": None, "$graph": DEFAULT_GRAPH})
        self.state = TemplateState(self.context, self.dataset, self.spec, abort_on_error=self.abort_on_error)
        for one_off in spec.one_offs:
            if not one_off.name:
                self.log_error(f"One-off resource has no name {one_off}")
            else:
                process_resource_spec(one_off.name, one_off, self.state)

    def log_error(self, message: str) -> None:
        logging.error(f"Row {self.row}: {message}")
        self.error_count += 1

    def process_row(self, data: dict) -> Dataset:
        """
        Process one row of data returning current state of RDF store for test purposes,
        may be new graph just for this row.
        """
        self.row += 1
        self.context["$row"] = self.row
        state = self.state.child(data)
        try:
            for rspec in self.spec.resources:
                if not rspec.name:
                    logging.error(f"Resource has no name {rspec}")
                else:
                    try:
                        process_resource_spec(rspec.name, rspec, state)
                    except Exception as resource_spec_error:
                        self.log_error(f"failed to process resource {rspec.name}: {resource_spec_error}")
        except Exception as err:
            self.log_error(f"processing failed with {err}")
        return self.dataset

    def bind_namespaces(self) -> None:
        """Set the namespace prefixes for the dataset."""
        nm = NamespaceManager(
            Graph(),
            # Suppress spurious namespaces
            bind_namespaces="core",
        )
        self.dataset.namespace_manager = nm
        for ns, uri in self.spec.namespaces.items():
            nm.bind(ns, uri)
        nm.bind("def", f"{self.spec.context['$datasetBase']}/def/", override=False, replace=False)

    def write_as_update(self) -> None:
        """Write the current state of the dataset as a SPARQL update."""
        with self.output as out:
            self._emit_prefixes(out)
            for g in self.dataset.graphs():
                if len(g) > 0:
                    if g.identifier.toPython() not in self.state.preserved_graphs:
                        out.write(f"DROP SILENT GRAPH <{g.identifier}> ;\n")
                    out.write("INSERT DATA {\n")
                    self._emit_graph(out, g)
                    out.write("};\n")

    def write_as_delete(self) -> None:
        """Write the current state of the dataset as a SPARQL update which deletes non-preserved graphs,
            and deletes triples from preserved graphs."""
        with self.output as out:
            if len(self.state.preserved_graphs) > 0:
                self._emit_prefixes(out)
            for g in self.dataset.graphs():
                if len(g) > 0:
                    if g.identifier.toPython() not in self.state.preserved_graphs:
                        out.write(f"DROP SILENT GRAPH <{g.identifier}> ;\n")
                    else:
                        out.write("DELETE DATA {\n")
                        self._emit_graph(out, g)
                        out.write("};\n")

    def _emit_prefixes(self, out:TextIO) -> None:
        defgraph = self.dataset.graph(DEFAULT_GRAPH)
        for ns, uri in defgraph.namespaces():
            out.write(f"PREFIX {ns}: <{uri}>\n")

    def _emit_graph(self, out:TextIO, g:Graph) -> None:
        if g.identifier != DEFAULT_GRAPH_ID:
            out.write(f"GRAPH <{g.identifier}> {{\n")
        for line in g.serialize(format="turtle").splitlines():
            if line.startswith("@prefix"):
                continue
            out.write(line)
            out.write("\n")
        if g.identifier != DEFAULT_GRAPH_ID:
            out.write("}\n")

    def finalize(self, fmt: str) -> bool:
        """
        Finalize processing, writing output in the requested format.
        Returns True if successful, False if aborted due to errors.
        """
        logging.info(f"Processed {self.row} lines")
        if self.error_count > 0:
            if self.abort_on_error:
                self.log_error(f"Aborting due to {self.error_count} errors")
                return False
            else:
                logging.info(f"Completed with {self.error_count} errors, skipping those rows")
        if fmt == "update":
            self.write_as_update()
        elif fmt == "delete":
            self.write_as_delete()
        else:
            with self.output as out:
                out.write(self.dataset.serialize(format=fmt))
        return True
