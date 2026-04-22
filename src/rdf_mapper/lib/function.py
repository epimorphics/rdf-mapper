
import base64
import datetime
import hashlib
import re
from collections.abc import Callable
from typing import Any

import dateparser
from rdflib import XSD
from rdflib.term import Literal

from rdf_mapper.lib.errors import PatternExpansionError
from rdf_mapper.lib.template_state import TemplateState

_CALL_PATTERN = re.compile(r"([\w]+)\s*\((.*)\s*\)")
_ARG_PATTERN = re.compile(r"""\s*(?P<arg>('([^']*)')|("([^"]*)")|([^\s,]+))\s*""")

_REGISTRY: dict[str, Callable] = {}

def register(name: str, func: Callable) -> None:
    _REGISTRY[name] = func

def get(name: str) -> Callable:
    fn = _REGISTRY.get(name)
    if fn and callable(fn):
        return fn
    if name in globals() and callable(globals()[name]):
        dfn = f"lambda value, state: {name}(value, state)"
        fn = eval(dfn, None)
        register(name, fn)
        return fn
    match = _CALL_PATTERN.match(name)
    if match:
        fnname = match.group(1).strip()
        args = match.group(2).strip()
        bindings: list[str] = []
        if len(args) > 0:
            for arg_match in _ARG_PATTERN.finditer(args):
                arg = arg_match.group("arg")
                if arg.startswith("'") and arg.endswith("'") or arg.startswith('"') and arg.endswith('"'):
                    bindings.append(arg)
                else:
                    bindings.append(f"state.get('{arg}', '{arg}')")
        if fnname in _REGISTRY:
            # When the function is in the registry it needs to be invoked using the __call__ method
            dfn = f"lambda value, state: _REGISTRY['{fnname}'].__call__(value, state, {', '.join(bindings)})"
        else:
            # Global functions can be invoked directly
            dfn = f"lambda value, state: {fnname}(value, state, {','.join(bindings)})"
        fn = eval(dfn, None)
        register(name, fn)
        return fn
    else:
        raise PatternExpansionError(f"Function '{name}' not found in registry")

def _noneOrEmpty(s: Any) -> bool:
    return s is None or type(s) is str and s == ''

def evaluate(call_string: str, value: Any, state: TemplateState) -> Any:
    fn = get(call_string)
    return fn.__call__(value, state)

def asInt3(s: str, state: TemplateState | None = None)-> int:
    """Return triple integer value of string, used for testing."""
    return int(s)*3

def asInt(s: Any, state: TemplateState | None = None) -> Literal | None:
    return Literal(int(float(s))) if not _noneOrEmpty(s) else None
    # return Literal(s, datatype=XSD.integer) if s else None

def asDecimal(s: Any, state: TemplateState | None = None) -> Literal | None:
    if _noneOrEmpty(s):
        return None
    if type(s) is float:
        return Literal(s, datatype=XSD.decimal)
    else:
        return Literal(float(s), datatype=XSD.decimal)


def asDateTime(s: Any, state: TemplateState | None = None) -> Literal | None:
    if _noneOrEmpty(s) or type(s) is not str:
        return None
    dt = dateparser.parse(s)
    return Literal(dt.isoformat(), datatype=XSD.dateTime) if dt else None

def asDate(s: str, state: TemplateState | None = None) -> Literal | None:
    if _noneOrEmpty(s) or type(s) is not str:
        return None
    dt = dateparser.parse(s)
    return Literal(dt.date().isoformat(), datatype=XSD.date) if dt else None

def asDateOrDatetime(s: str, state: TemplateState | None = None) -> Literal | None:
    if _noneOrEmpty(s) or type(s) is not str:
        return None
    if re.fullmatch(r"[12]\d{3}", s):
        return Literal(f'{s}-01-01', datatype=XSD.date)
    else:
        dt = dateparser.parse(s)
        if dt:
            if dt.time() == datetime.time(0,0):
                return Literal(dt.date().isoformat(), datatype=XSD.date)
            else:
                return Literal(dt.isoformat(), datatype=XSD.dateTime)
        else:
            return None

def _foldForComparison(v: Any) -> Any:
    if type(v) is str:
        return v.lower()
    return v

def asBoolean(s: Any, state: TemplateState | None = None, *args) -> Literal:
    if s is None:
        return Literal(False, datatype=XSD.boolean)
    if len(args) > 0:
        return Literal(_foldForComparison(s) in [_foldForComparison(a) for a in args], datatype=XSD.boolean)
    return Literal(_foldForComparison(s) in ["yes", "true", "ok", "1", 1, float(1)], datatype=XSD.boolean)

def _string_check(s: Any, func_name: str, permissive: bool = False) -> str:
    if s is None:
        raise ValueError(f"{func_name} function does not accept None as input")
    if isinstance(s, Literal):
        return s.value
    if type(s) is not str:
        if permissive:
            return str(s)
        else:
            raise ValueError(f"{func_name} function only accepts strings, or Literals as input but found {type(s)}")
    return s

def trim(s: Any, state: TemplateState | None = None) -> str:
    s = _string_check(s, "trim")
    return s.strip()

def toLower(s: Any, state: TemplateState | None = None) -> str:
    s = _string_check(s, "toLower")
    return s.lower()

def toUpper(s: Any, state: TemplateState | None = None) -> str:
    s = _string_check(s, "toUpper")
    return s.upper()

def slug(s: Any, state: TemplateState | None = None) -> str:
    s = _string_check(s, "slug", permissive=True)
    return '-'.join(s.lower().split()).replace('%', '_').replace('/', '_').replace('[', '_').replace(']', '_')

def splitComma(s: Any, state: TemplateState | None = None) -> list[str]:
    s = _string_check(s, "splitComma")
    return re.split(r"\s*,\s*", s)

def split(s: Any, state: TemplateState, reg: str) -> list[str]:
    s = _string_check(s, "split")
    return re.split(reg, s)

_EXPR_CACHE: dict[str, Any] = {}

def expr(s: Any, state: TemplateState | None = None, expression: str = "") -> Any:  # noqa: A001
    code = _EXPR_CACHE.get(expression)
    if not code:
        code = compile(expression, "<String>", "eval")
        _EXPR_CACHE[expression] = code
    return eval(code, {}, {"x": s, "state": state})

def hash(arg: str | None, state: TemplateState, *keys: str) -> str:  # noqa: A001
    _hash = hashlib.sha1()
    if arg:
        _hash.update(bytes(arg,"UTF-8"))
    for key in keys:
        _hash.update(bytes(str(key),"UTF-8"))
    return base64.b32hexencode(_hash.digest()).decode("UTF-8")

def now(_: Any, state: TemplateState) -> Literal:
    return Literal(datetime.datetime.now().isoformat(), datatype=XSD.dateTime)

def to_entries(data: Any, state: TemplateState) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        raise ValueError(f"to_entries expecting data to be a dict but found {data}")
    return [{"$key": key, "$value": value} for key, value in filter(lambda item: not item[0].startswith("$"), data.items())]

