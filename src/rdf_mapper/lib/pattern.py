import re
from typing import Any, Callable, Iterable, Iterator, Mapping, Protocol

from rdflib import Literal
from rdflib.term import Identifier

from rdf_mapper.lib import function
from rdf_mapper.lib.errors import MissingValueWarning
from rdf_mapper.lib.template_state import TemplateState

_CURI_PATTERN = re.compile(r"([_A-Za-z][\w\-\.]*):([\w\-\.]+)")

def _expand_curi(uriref: str, namespaces: Mapping[str,str]) -> str:
    match = _CURI_PATTERN.fullmatch(uriref)
    if match:
        ns = namespaces.get(match.group(1))
        if ns:
            return ns + match.group(2)
    return uriref


class PipelineFunction(Protocol):
    def __call__(self, lit: Literal|None, *args: str) -> Literal:
        ...

class Pattern:

    _LANGSTRING_PATTERN = re.compile(r"^(.+)@([\w\-]+)$", re.DOTALL)
    _DT_PATTERN = re.compile(r"^(.+)\^\^<([^>]+)>$", re.DOTALL)
    _VARPATTERN = re.compile(r"{([^}]*)}")
    _PIPEPATTERN = re.compile(r"\s*\|\s*")

    def __init__(self, pattern: str):
        self._patternString = pattern
        self._patternType = None
        if self._LANGSTRING_PATTERN.match(pattern):
            self._patternType = "langstring"
        elif self._DT_PATTERN.match(pattern):
            self._patternType = "datatype"
        self._call_chain: list[Callable[[Identifier|None, TemplateState], Iterator[Identifier]]] = []
        self._parsePattern()

    def execute(self, state: TemplateState) -> Iterator[Identifier]:
        values = list(self._call_chain[0](None, state))
        for func in self._call_chain[1:]:
            values = list(self._concat(v, result) for v in values for result in func(v, state))
        yield from filter(lambda v: v is not None, map(lambda v: self._wrap_literal(v, state.spec.namespaces), values)) #type: ignore

    def _wrap_literal(self, node: Identifier|None, namespaces: Mapping[str, str]) -> Identifier|None:
        if node is None:
            return None
        if isinstance(node, Literal) and isinstance(node.value, str):
            # Attempt to parse language tagged string or datatype from the literal value
            # if it is in the form "value@lang" or "value^^datatype"
            langstring_match = self._LANGSTRING_PATTERN.match(node.value)
            if langstring_match:
                return Literal(langstring_match.group(1), lang=langstring_match.group(2))
            dt_match = self._DT_PATTERN.match(node.value)
            if dt_match:
                return Literal(dt_match.group(1), datatype= _expand_curi(dt_match.group(2), namespaces))
            if self._patternType == "langstring" or self._patternType == "datatype":
                # If the pattern is a langstring or datatype pattern, but the output value does not match the expected format.
                # we should not yield it as a literal
                return None
        return node

    def _concat(self, node1: Identifier|None, node2: Identifier) -> Identifier:
        if node1 is None:
            return node2
        if isinstance(node1, Literal) and isinstance(node2, Literal):
            return Literal(str(node1.value) + str(node2.value))
        else:
            return Literal(str(node1) + str(node2))

    def _parsePattern(self) -> None:
        to_parse = self._patternString
        self._parse_variables_and_statics(to_parse)

    def _parse_variables_and_statics(self, to_parse: str) -> None:
        last_index = 0
        for var_match in self._VARPATTERN.finditer(to_parse):
            if var_match.start() > last_index:
                self._call_chain.append(static_value(to_parse[last_index:var_match.start()]))
            self._parse_variable_expansion(var_match.group(1))
            last_index = var_match.end()
        if last_index < len(to_parse):
            self._call_chain.append(static_value(to_parse[last_index:]))

    def _parse_variable_expansion(self, var_string: str) -> None:
        var_parts = self._PIPEPATTERN.split(var_string)
        var_name = var_parts[0].strip()
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
        values = self._call_chain[0](None, state)
        if isinstance(values, Iterable) and not isinstance(values, str):
            values = list(values)
        else:
            values = [values]
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

