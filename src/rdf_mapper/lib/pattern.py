import re
from typing import Any, Callable, Iterable, Iterator, Protocol

from rdflib import Literal
from rdflib.term import Identifier

from rdf_mapper.lib.errors import PatternExpansionError, MissingValueWarning
from rdf_mapper.lib.template_state import TemplateState
from rdf_mapper.lib import function


class PipelineFunction(Protocol):
    def __call__(self, lit: Literal|None, *args: str) -> Literal:
        ...

class Pattern:
    
    _LANGSTRING_PATTERN = re.compile(r"^(.+)@([\w\-]+)$", re.DOTALL)
    _DT_PATTERN = re.compile(r"^(.+)\^\^(<[^>]+>)$", re.DOTALL)
    _VARPATTERN = re.compile(r"{([^}]*)}")
    _PIPEPATTERN = re.compile(r"\s*\|\s*")

    def __init__(self, pattern: str):
        self.type = "plain"
        self.lang = None
        self.datatype = None
        self._patternString = pattern
        self._call_chain: list[Callable[[Identifier|None, TemplateState], Iterator[Identifier]]] = []
        self._parsePattern()
    
    def execute(self, state: TemplateState) -> Iterator[Identifier]:
        values = list(self._call_chain[0](None, state))
        for func in self._call_chain[1:]:
            values = list(self._append(v, result) for v in values for result in func(v, state))
        yield from map(lambda v: self._wrap_literal(v), filter(lambda v: v is not None, values))

    def _wrap_literal(self, node: Identifier) -> Identifier:
        if isinstance(node, Literal):
            if self.type == "langstring" and self.lang:
                return Literal(node.value, lang=self.lang)
            elif self.type == "datatype" and self.datatype:
                return Literal(node.value, datatype=self.datatype)
        if self.type == "langstring":
            return Literal(str(node), lang=self.lang)
        elif self.type == "datatype":
            return Literal(str(node), datatype=self.datatype)
        else:
            return node

    def _append(self, node1: Identifier|None, node2: Identifier) -> Identifier:
        if node1 is None:
            return node2
        if isinstance(node1, Literal) and isinstance(node2, Literal):
            return Literal(str(node1.value) + str(node2.value))
        else:
            return Literal(str(node1) + str(node2))

    def _parsePattern(self):
        to_parse = self._patternString
        to_parse = self._parse_langstring(to_parse)
        to_parse = self._parse_datatype(to_parse)
        self._parse_variables_and_statics(to_parse)
    
    def _parse_langstring(self, to_parse: str) -> str:
        langstring_match = self._LANGSTRING_PATTERN.match(to_parse)
        if langstring_match:
            self.type = "langstring"
            self.lang = langstring_match.group(2)
            return langstring_match.group(1)
        return to_parse
        
    def _parse_datatype(self, to_parse: str) -> str:
        dt_match = self._DT_PATTERN.match(to_parse)
        if dt_match:
            self.type = "datatype"
            self.datatype = dt_match.group(2)
            return dt_match.group(1)
        return to_parse
    
    def _parse_variables_and_statics(self, to_parse: str):
        last_index = 0
        for var_match in self._VARPATTERN.finditer(to_parse):
            if var_match.start() > last_index:
                self._call_chain.append(static_value(to_parse[last_index:var_match.start()]))
            self._parse_variable_exapnsion(var_match.group(1))
            last_index = var_match.end()
        if last_index < len(to_parse):
            self._call_chain.append(static_value(to_parse[last_index:]))
    
    def _parse_variable_exapnsion(self, var_string: str) -> None:
        var_parts = self._PIPEPATTERN.split(var_string)
        var_name = var_parts[0]
        var_expansion = VariableExpansion(var_name, var_parts[1:])
        self._call_chain.append(var_expansion.execute)
    
class VariableExpansion:
    def __init__(self, var_name: str, functions: list[str]):
        self.var_name = var_name
        self.functions = functions
        self._call_chain: list[Callable] = []
        if var_name:
            self._call_chain.append(_variable_value(var_name))
        for function_call_string in functions:
            self._call_chain.append(function.get(function_call_string))

    def execute(self,_:Any, state: TemplateState) -> Iterator[Identifier]:
        values = list(self._call_chain[0](None, state))
        for func in self._call_chain[1:]:
            results = []
            for v in values:
                result = func(v, state)
                if isinstance(result, Iterable) and not isinstance(result, str):
                    results.extend(result)
                else:
                    results.append(result)
            values = results
        yield from map(lambda v: Literal(v) if not isinstance(v, Identifier) else v, filter(lambda v: v is not None, values))


def static_value(value: str) -> Callable[[Identifier|None, TemplateState], Iterator[Literal]]:
    def _static_value(_: Identifier|None, __: TemplateState) -> Iterator[Literal]:
        yield Literal(value)
    return _static_value


def _variable_value(var_name: str) -> Callable[[Identifier|None, TemplateState], Iterator[Any]]:
    def _variable_value(_: Identifier|None, state: TemplateState) -> Iterator[Any]:
        if var_name in state.context:
            yield state.context[var_name]
        else:
            raise MissingValueWarning(f"Variable '{var_name}' not found in context")
    return _variable_value

