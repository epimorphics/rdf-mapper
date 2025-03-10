"""
    Processor to generate RDF transformed output from each row of source data based on mapper spec.
"""

import logging
from typing import TextIO

from rdflib import Dataset

from rdf_mapper.lib.mapper_spec import MapperSpec
from rdf_mapper.lib.template_state import TemplateState
from rdf_mapper.lib.template_support import process_resource_spec

DEFAULT_GRAPH = "urn:x-rdflib:default"

class TemplateProcessor:

    def __init__(self, spec: MapperSpec, filename: str, output: TextIO) -> None:
        self.spec = spec
        self.output = output
        self.dataset = Dataset()   # TODO streaming version
        self.row = 0
        self.context = self.spec.context.new_child({'$file' : filename, '$row' : None, '$graph' : DEFAULT_GRAPH})
        self.state = TemplateState(self.context, self.dataset, self.spec)
        for one_off in spec.one_offs:
            if not one_off.name:
                logging.error(f"One-off resource has no name {one_off}")
            else:
                process_resource_spec(one_off.name, one_off, self.state)

    def process_row(self, data: dict) -> Dataset:
        """
          Process one row of data returning current state of RDF store for test purposes,
          may be new graph just for this row.
        """
        self.row += 1
        self.context['$row'] = self.row
        state = self.state.child(data)
        try:
            for rspec in self.spec.resources:
                if not rspec.name:
                    logging.error(f"Resource has no name {rspec}")
                else:
                    process_resource_spec(rspec.name, rspec, state)
        except Exception as err:
            logging.error(f"Failure on row {self.row} with {err}")
        return self.dataset

    def bind_namespaces(self) -> None:
        defgraph = self.dataset.graph(DEFAULT_GRAPH)
        for ns, uri in self.spec.namespaces.items():
            defgraph.bind(ns, uri)
        defgraph.bind("def", f"{self.spec.context['$datasetBase']}/def/", override=False)

    def finalize(self) -> None:
        logging.info(f"Processed {self.row} lines")
        self.bind_namespaces()
        self.output.write(self.dataset.graph(DEFAULT_GRAPH).serialize(format='turtle'))
        self.output.close()
