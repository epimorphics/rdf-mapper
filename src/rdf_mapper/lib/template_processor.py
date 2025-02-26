"""
    Processor to generate RDF transformed output from each row of source data based on mapper spec.
"""

from rdf_mapper.lib.mapper_spec import MapperSpec
from rdflib import Graph
from typing import TextIO
from rdf_mapper.lib.template_support import process_resource_spec
from rdf_mapper.lib.template_state import TemplateState
import logging

class TemplateProcessor:

    def __init__(self, spec: MapperSpec, filename: str, output: TextIO) -> None:    
        self.spec = spec
        self.output = output
        self.graph = Graph()   # TODO streaming version
        self.row = 0
        self.context = self.spec.context.new_child({'$file' : filename, '$row' : None})
        self.state = TemplateState(self.context, self.graph, self.spec)
        for one_off in spec.one_offs:
            process_resource_spec(one_off.name, one_off, self.state)

    def process_row(self, data: dict) -> Graph:
        """Process one row data returning current state of graph for test purposes, may be new graph just for this row."""
        self.row += 1
        self.context['$row'] = self.row
        state = self.state.child(data)
        try:
            for rspec in self.spec.resources:
                process_resource_spec(rspec.name, rspec, state)
        except Exception as err:
            logging.error(f"Failure on row {self.row} with {err}")
        return self.graph

    def finalize(self) -> None:
        logging.info(f"Processed {self.row} lines")
        self.output.write(self.graph.serialize(format='turtle'))
        self.output.close()
