"""
    Functions implementing all the mechanisms of template expansion and substitution.

    Primary entry point is process_resource_spec, though some of the machinery such as
    pattern_expand and uri_expand may be usable in other contexts.

    Built in processing functions and registration of externally defined functions
    are also implemented here since they need access to parts of this machinery.
"""

import base64
import datetime
import hashlib
import logging
import re
import uuid
from collections.abc import Callable, Mapping
from typing import Any, Union
from urllib.parse import urljoin

import dateparser
from rdflib import RDF, SKOS, XSD, BNode, IdentifiedNode, Literal, URIRef, term

from rdf_mapper.lib.mapper_spec import PropSpec, ResourceSpec
from rdf_mapper.lib.reconcile import MatchResult, ReconcileRequest, requestReconcile
from rdf_mapper.lib.template_state import ReconciliationRecord, TemplateState

_VARPATTERN = re.compile(r"{([^}]*)}")

def pattern_expand(template: str, state: TemplateState) -> str:
    """Return template with var references {var} expanded from the given dict-like context.

       Allows pattern to include a chain of transforms {var | fn | fn2}.
       If the var references are embedded "foo{var}bar" the var will be converted to str.
       If the whole pattern is a var reference "{var}" can return a typed value if the
       context or any transformation functions return a typed value.
    """
    if _VARPATTERN.fullmatch(template):
        return valueof_var(template[1:-1], state)
    else:
        last_match = 0
        fragments = []
        for m in _VARPATTERN.finditer(template):
            prior = template[last_match:m.start()]
            fragments.append(prior)
            last_match = m.end()
            varname = m.group()[1:-1]
            val = valueof_var(varname, state)
            if val:
                fragments.append(str(val))
            else:
                fragments.append(m.group())
        fragments.append(template[last_match:])
        return ''.join(fragments)

_PIPEPATTERN = re.compile(r"\s*\|\s*")

def valueof_var(var: str, state: TemplateState) -> Any:
    """Return the value of the var from the context.

       Supports "var | fn | fn" syntax for normalisation and processing of the value.
    """
    varname, *chain = _PIPEPATTERN.split(var)
    val = state.get(varname.strip())
    if isinstance(val, str):
        val = val.strip()
    for fnname in chain:
        fn = find_fn(fnname)
        if fn:
            if isinstance(val, list):
                result = []
                for i, v in enumerate(val):
                    result.append(fn(v, state.child({"$listIndex": i})))
                val = result
            else:
                val = fn(val, state)
        else:
            raise ValueError(f"Could not find function {fnname}")
    if val is None or val == "":
        raise ValueError(f"could not find value for '{varname}'")
    return val

_POOR_URI_CHARS = re.compile(r"[^\w\-]+")

def normalize(s: str) -> str:
    norm = _POOR_URI_CHARS.sub("_",s.strip())
    if norm.endswith("_"):
        norm = norm[:-1]
    if norm.startswith("_"):
        norm = norm[1:]
    return norm

_CURI_PATTERN = re.compile(r"([_A-Za-z][\w\-\.]*):([\w\-\.]+)")
_URI_PATTERN = re.compile(r"(https?|file|urn)://.*")   # TODO Support other schemes
_HASH_PATTERN = re.compile(r"hash\s?\(([^)]*)\)$")
_COMMA_SPLIT = re.compile(r"\s*,\s*")

def uri_expand(pattern: str, namespaces: Mapping[str,str], state: TemplateState) -> str:
    """Expand a URI pattern.

       Supports pattern forms:
       name   - simple name, place in datasets def namespace
       <row>  - create data URI base on file and row, for one_offs row is None and omit that segment
       <uuid> - create data URI based on a random UUID
       <hash(col1,...)> - create data URI based on hash of one or more columns in the data
       <http://foo{bar}> - expand any {} references in pattern and create as absolute URI
       <prefix:local>  - Curie style, using prefixes from builtin or project specific namespaces
    """
    if pattern.startswith("<") and pattern.endswith(">"):
        uriref = pattern[1:-1]
        if uriref == "uuid":
            uriref = str(uuid.uuid4())
        elif uriref == "row":
            row = state.get('$row')
            if row:
                uriref = normalize(state.get('$file')) + "-" + str(row) # type: ignore
                if state.get('$listIndex') is not None:
                    # if nested resources in some list scan then need to include list index in generated resource ID
                    uriref = str(state.get('$listIndex')) + "/" + uriref
            else:
                uriref = None
        elif uriref == "parent":
            parent = state.get("$parentID")
            if parent:
                uriref = parent + "/" + state.get("$resourceID") # type: ignore - know that $resourceID is set
                if state.get('$listIndex') is not None:
                    uriref = uriref + "/" + str(state.get('$listIndex'))
            else:
                uriref = None
        elif _HASH_PATTERN.fullmatch(uriref):
            params = _HASH_PATTERN.fullmatch(uriref).group(1) # type: ignore
            params = _COMMA_SPLIT.split(params)
            _hash = hashlib.sha1()
            for p in params:
                if p.startswith("'") and p.endswith("'"):
                    _hash.update(bytes(p[1:-1],"UTF-8"))
                else:
                    _hash.update(bytes(str(state.get(p)),"UTF-8"))
            uriref = base64.b32hexencode(_hash.digest()).decode("UTF-8")
        else:
            uriref = pattern_expand(uriref, state)
            if uriref and isinstance(uriref, str):
                uriref = _expand_curi(uriref, namespaces)
                match = _CURI_PATTERN.fullmatch(uriref)
                if match:
                    ns = namespaces.get(match.group(1))
                    if ns:
                        uriref = ns + match.group(2)
            else:
                raise ValueError(f"Could not expand uri reference {pattern}")
        if uriref:
            if not _URI_PATTERN.fullmatch(uriref) :
                uriref = urljoin(f"{state.get('$datasetBase')}/data/{state.get('$resourceID')}/", uriref)
        else:
            uriref = f"{state.get('$datasetBase')}/data/{state.get('$resourceID')}"
        return uriref
    else:
        # Simple string, create as def in dataset namespace
        _id = f"{state.get('$datasetBase')}/def/{normalize(pattern)}"
        if state.spec.auto_declare:
            _record_implicit_prop(pattern, _id, None, state)
        return _id

def _expand_curi(uriref: str, namespaces: Mapping[str,str]) -> str:
    match = _CURI_PATTERN.fullmatch(uriref)
    if match:
        ns = namespaces.get(match.group(1))
        if ns:
            return ns + match.group(2)
    return uriref


_LANGSTRING_PATTERN = re.compile(r"^(.+)@([\w\-]+)$")
_DT_PATTERN = re.compile(r"^(.+)\^\^(<[^>]+>)$")

def value_expand(pattern: str, namespaces: Mapping[str,str], state: TemplateState) -> Union[None, term.Identifier, list[term.Identifier]]:  # noqa: E501
    """Expand a value template to an RDF value.

       Supports pattern forms:
       <uri-ref>        - uri reference using any of URI patterns in uri_expand
       <::backref>      - uri reference back to an already produced resource
       foo{var}bar      - templated string values
       foo{var}var@lang - templated language string values (language can be templated)
       {var | fn | fn}  - literal value derived from var by series of transformations, may result in typed value

       Transform functions may be builtin or registered via register_fn.
       Builtins include: asInt asDecimal asDate
    """
    if pattern.startswith("<") and pattern.endswith(">") and not _DT_PATTERN.fullmatch(pattern):
        if pattern.startswith("<::"):
            return state.backlinks.get(pattern[3:-1])
        else:
            return URIRef(uri_expand(pattern, namespaces, state))
    else:
        val = pattern_expand(pattern, state)
        return _value_to_rdf(val, state)

def _value_to_rdf(val: Any, state:TemplateState) -> Union[None, term.Identifier, list[term.Identifier]]:
    if isinstance(val, term.Identifier):
        return val
    elif val is None:
        return None
    elif isinstance(val, list):
        return [_value_to_rdf(v, state) for v in val]  # type: ignore - TODO better typing for single depth list
    elif isinstance(val, str):
        if match := _LANGSTRING_PATTERN.fullmatch(val):
            return Literal(match.group(1), lang=match.group(2))
        elif match := _DT_PATTERN.fullmatch(val):
            dt_uri = uri_expand(match.group(2), state.spec.namespaces, state)
            return Literal(match.group(1), datatype=dt_uri)
        else:
            return Literal(val)
    else:
        return Literal(val)

def process_resource_spec(name: str, rs: ResourceSpec, state: TemplateState) -> IdentifiedNode | None:
    """Process a single resource specification in the current context."""
    state.add_to_context("$resourceID", name)
    # properties = rs.properties  # TODO check why this was there but unused
    namespaces = state.spec.namespaces

    # If the resource spec has a requires dict, check the row for matching values
    if rs.requires:
        for key in rs.requires:
            value = state.get(key)
            expected = rs.requires.get(key)
            if expected is not None:
                if type(expected) is list:
                    if value not in expected:
                        logging.warning(
                            f"Skipping resource {rs.name} on row {state.get('$row')} because value for {key} is {value}, which is not one of the required values {expected}.")  # noqa: E501
                        return None
                elif value != expected:
                    logging.warning(
                        f"Skipping resource {rs.name} on row {state.get('$row')} because value for {key} is {value}, which is different from the required value {expected}.")  # noqa: E501
                    return None
            elif value is None:
                logging.warning(f"Skipping resource {rs.name} on row {state.get('$row')} because there is no value for {key}.")
                return None
            elif value == '':
                logging.warning(f"Skipping resource {rs.name} on row {state.get('$row')} because value for {key} is an empty string.")
                return None

    # If the resource spec has an unless dict, check the row for non-matching values
    if rs.unless:
        for key in rs.unless:
            value = state.get(key)
            unless_value = rs.unless.get(key)
            if unless_value is None and value is not None and value != '':
                logging.warning(
                    f"Skipping resource {rs.name} on row {state.get('$row')} because value for {key} is not empty."
                )
                return None
            elif type(unless_value) is list:
                if value in unless_value:
                    logging.warning(
                        f"Skipping resource {rs.name} on row {state.get('$row')} because value for {key}  ({value}) is one of the filtered values {unless_value}."
                    )
                    return None
            elif unless_value is not None and value == unless_value:
                logging.warning(
                    f"Skipping resource {rs.name} on row {state.get('$row')} because value for {key} is {value}."
                )
                return None

    # Check for switch of graph
    if rs.graph:
        graph = uri_expand(rs.graph, namespaces, state)
        state = state.switch_to_graph(graph, rs.preserved_graph)

    # If we have no URI assignment default to the row pattern
    id_template = rs.find_prop_defn("@id") or "<row>"
    if id_template == "<_>":
        resource = BNode()
    else:
        _id =uri_expand(id_template, namespaces, state)
        resource = URIRef(_id)
    state.backlinks[name] = resource
    state.add_to_context("$parentID", str(resource))

    # Use an assigned type or default
    type_template = rs.find_prop_defn("@type")
    if not type_template and state.spec.auto_declare:
        type_template = "<{$datasetBase}/def/{$resourceID}>"
        _id = uri_expand(type_template, namespaces, state)
        _record_implicit_class(name, _id, rs.spec.get("comment"), state)
        type_uri = URIRef(_id)
        state.add_to_graph((resource, RDF.type, type_uri))
    elif type_template:
        type_uri = URIRef(uri_expand(type_template, namespaces, state))
        state.add_to_graph((resource, RDF.type, type_uri))

    # Process the properties
    for (prop, template) in rs.properties:
        try:
            process_property_value(resource, prop, template, state)
        except ValueError as ex:
            if prop != "<rdfs:comment>":
                # The rdfs:comment guard is a kludge to reduce noise when auto declaring properties and classes
                logging.warning(f"Skipping {prop} on row {state.get('$row')} because {ex}")
        except Exception as err:
            raise ValueError(f"Failed to process property {prop} on row {state.get('$row')}: {err}") from err
    return resource

def process_property_value(resource: IdentifiedNode, prop: str, template: Any, state: TemplateState) -> None:
    """Process a single property expansion."""
    if prop == "@id" or prop == "@type" or prop == "@graph":
        return   # already processed

    if isinstance(template, list):
        # Multiple expansions defined for this property
        for template_item in template:
            try:
                process_property_value(resource, prop, template_item, state)
            except ValueError as ex:
                logging.warning(f"Skipping {prop} on row {state.get('$row')} because {ex}")
        return

    # Check for inverse property
    inverse = prop.startswith("^")
    if inverse:
        prop = prop[1:]

    # Check for use of property specifications in the template or imports
    namespaces = state.spec.namespaces
    prop_spec: PropSpec | None = None
    if prop.startswith(":"):
        prop_spec = state.spec.propertySpecs.get(prop[1:])
        if prop_spec:
            (prop, template) = prop_spec.propValueTemplate(template)
            if prop_spec.cls:
                class_ref = URIRef(uri_expand(prop_spec.cls, namespaces, state))
                state.add_to_graph((resource, RDF.type, class_ref))
        else:
            raise ValueError(f"could not find property specification {prop}")

    propref = URIRef(uri_expand(prop, namespaces, state))
    propname = prop
    if prop_spec:
        if state.spec.auto_declare:
            _record_implicit_prop(prop_spec.name,  str(propref), prop_spec.spec.get("comment"), state)
        propname = prop_spec.name

    if isinstance(template, str):
        if template == "":
            template = "{" + prop + "}"
        value = value_expand(template, namespaces, state.child({"$prop": propname}))
    elif isinstance(template, dict):
        rs = ResourceSpec(template)
        if not rs.name:
            raise ValueError(f"Resource spec for property {prop} has no name")
        value = process_resource_spec(rs.name, rs, state)
    else:
        raise NotImplementedError("Implement inline property specs")

    if isinstance(value, list):
        for v in value:
            state.add_to_graph((resource, propref, v))
    else:
        if value is not None:
            if inverse:
                triple = (value, propref, resource)
            else:
                triple = (resource, propref, value)
            state.add_to_graph(triple)
        elif prop_spec and  prop_spec.required:
            raise ValueError(f"Value missing for required property {prop_spec.name}, pattern: {template}")
        # else do nothing, missing value but not required

_AUTO_CLASS_SPEC = ResourceSpec({
    "name": "AUTO_CLASS",
    "properties": {
        "@id" : "<{id}>",
        "@type" : "<owl:Class>",
        "<rdfs:label>": "{label}",
        "<rdfs:comment>": "{comment}",
    }
})

def _record_implicit_class(name: str, _id: str, comment: str | None, state: TemplateState) -> None:
    if not state.record_auto_emit("class", name):
        _create_resource({"id" : _id, "label": name, "comment": comment}, state, _AUTO_CLASS_SPEC)

_AUTO_PROP_SPEC = ResourceSpec({
    "name": "AUTO_PROP",
    "properties": {
        "@id" : "<{id}>",
        "@type" : "<rdf:Property>",
        "<rdfs:label>": "{label}",
        "<rdfs:comment>": "{comment}",
    }
})

def _record_implicit_prop(name: str, _id: str, comment: str | None, state: TemplateState) -> None:
    if not state.record_auto_emit("prop", name):
        _create_resource({"id" : _id, "label": name, "comment": comment}, state, _AUTO_PROP_SPEC)

# Built in transformation functions, provisional

_FUN_REGISTRY: dict[str, Callable] = {}

def register_fn(name: str, fn: Callable) -> None:
    """Add a named function to the register of operation that can be used in var processing chains."""
    _FUN_REGISTRY[name] = fn

_CALL_PATTERN = re.compile(r"([\w]+)\s*\((.*)\s*\)")

def find_fn(call: str) -> Callable | None:
    """
    Return the function corresponding to a function call spec.

    If the call is a simply a function name then look it up in globals or registry.
    If it looks like a call with argument then construct a matching lambda and register that.
    """
    fn = globals().get(call) or _FUN_REGISTRY.get(call)
    if not fn:
        match = _CALL_PATTERN.fullmatch(call)
        if match:
            fnname = match.group(1).strip()
            args = match.group(2).strip()
            bindings: list[str] = []
            if len(args) > 0:
                for arg in _COMMA_SPLIT.split(args):
                    if not (arg.startswith("'") and arg.endswith("'")) or (arg.startswith('"') and arg.endswith('"')):
                        bindings.append(f"state.get('{arg}') or {arg}")
                    else:
                        bindings.append(arg)
            if fnname in _FUN_REGISTRY:
                # When the function is in the registry it needs to be invoked using the __call__ method
                dfn = f"lambda value, state: _FUN_REGISTRY['{fnname}'].__call__(value, state, {', '.join(bindings)})"
            else:
                # Global functions can be invoked directly
                dfn = f"lambda value, state: {fnname}(value, state, {','.join(bindings)})"
            fn = eval(dfn)
            # print(f"Registering {dfn}")
            register_fn(call, fn)
    return fn

def asInt3(s: str, state: TemplateState | None = None)-> int:
    """Return triple integer value of string, used for testing."""
    return int(s)*3

def asInt(s: str, state: TemplateState | None = None) -> Literal | None:
    return Literal(int(float(s))) if s else None
    # return Literal(s, datatype=XSD.integer) if s else None

def asDecimal(s: str, state: TemplateState | None = None) -> Literal | None:
    return Literal(s, datatype=XSD.decimal) if s else None

def asDateTime(s: str, state: TemplateState | None = None) -> Literal | None:
    if s is None:
        return None
    dt = dateparser.parse(s)
    return Literal(dt.isoformat(), datatype=XSD.dateTime) if dt else None

def asDate(s: str, state: TemplateState | None = None) -> Literal | None:
    if s is None:
        return None
    dt = dateparser.parse(s)
    return Literal(dt.date().isoformat(), datatype=XSD.date) if dt else None

def asDateOrDatetime(s: str, state: TemplateState | None = None) -> Literal | None:
    if s is None:
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

def asBoolean(s: str, state: TemplateState | None = None, *args) -> Literal:
    if len(args) > 0:
        return Literal(s.lower() in [a.lower() for a in args], datatype=XSD.boolean)
    return Literal(s.lower() in ["yes", "true", "ok", "1"], datatype=XSD.boolean)

def trim(s: str, state: TemplateState | None = None) -> str | None:
    return s.strip() if s else None

def toLower(s: str, state: TemplateState | None = None) -> str | None:
    return s.lower() if s else None

def toUpper(s: str, state: TemplateState | None = None) -> str | None:
    return s.upper() if s else None

def splitComma(s: str, state: TemplateState | None = None) -> list:
    return _COMMA_SPLIT.split(s) if s else []

def split(s: str, state: TemplateState, reg: str) -> list:
    return re.split(reg, s) if s else []

_EXPR_CACHE: dict[str, Any] = {}

def expr(s: Any, state: TemplateState | None = None, expression: str = "") -> Any:  # noqa: A001
    code = _EXPR_CACHE.get(expression)
    if not code:
        code = compile(expression, "<String>", "eval")
        _EXPR_CACHE[expression] = code
    return eval(code, {}, {"x": s, "state": state})

def _create_resource(data: dict, state: TemplateState, rs: ResourceSpec) -> IdentifiedNode | None:
    if not rs.name:
        raise ValueError("Resource spec must have a name, {rs}")
    return process_resource_spec(rs.name, rs, state.child(data))

def map_to(data: dict, state: TemplateState, rsname: str) -> IdentifiedNode | None:
    if not data:
        return None
    rs = state.spec.embedded_resources.get(rsname)
    if not rs:
            raise ValueError(f"map_to could not find embedded template called {rsname}")
    if not isinstance(data, dict):
        raise ValueError(f"map_to expecting data to be a dict but found {data}")
    return _create_resource(data, state, rs)

def map_by(data: str, state: TemplateState, mapping_name: str) -> term.Identifier | None:
    if not data:
        return None
    mapping = state.spec.mappings.get(mapping_name)
    if not mapping:
        raise ValueError(f"map_by could not find mapping called {mapping_name}")
    if not isinstance(data, str):
        raise ValueError(f"map_by expecting data to be a string but found {data}")
    mapped = mapping.get(data)
    if mapped is None:
        raise ValueError(f"map_by could not find mapping for {data} in {mapping_name}")
    value = value_expand(mapped, state.spec.namespaces, state)
    if value is None:
        raise ValueError(f"map_by could not complete mapping for {data} in {mapping_name}")
    elif isinstance(value, list):
        logging.warning(f"map_by mapping for {data} in {mapping_name} resulted in a list, only using first value")
        return value[0]
    else:
        return value

def hash(arg: str | None, state: TemplateState, *keys: str) -> str:  # noqa: A001
    _hash = hashlib.sha1()
    if arg:
        _hash.update(bytes(arg,"UTF-8"))
    for key in keys:
        _hash.update(bytes(str(key),"UTF-8"))
    return base64.b32hexencode(_hash.digest()).decode("UTF-8")

_PROXY_CONCEPT_SPEC = {
    "properties" : {
        "@id" : "<hash(key,keytype)>",
        "@type" : "<{keytype}>",
        "<skos:prefLabel>" : "{key}"
    }
}

def reconcile(key: str, state: TemplateState, name: str, _type: str | None = None, endpoint: str | None = None,
              filters: list = [], skip_placeholders: bool = False) -> IdentifiedNode:
    """Reconcile the key/type.

       name is used as local resource name if need to create a proxy.
       Assumes there's a reconciliationAPI key in the context.
       """
    _id = state.reconciled_ref(key, _type)
    if not _id:
        # TODO batch up reconciliation requests, instead of on-the-fly
        api = endpoint or state.get("$reconciliationAPI")
        if not api:
            raise ValueError("No reconciliationAPI configured")
        namespaces = state.spec.namespaces
        if _type:
            _type = _expand_curi(_type, namespaces)
        if filters:
            filters = [(_expand_curi(p, namespaces),_expand_curi(v, namespaces)) for p,v in filters]
        matches = requestReconcile(api, [ReconcileRequest(key, _type, filters)])
        if len(matches) == 1:
            matchResult: MatchResult = matches[0]
            keydesc = f"{key}-{_type}" if _type else key
            if matchResult.match:
                logging.info(f"Reconciled {keydesc} to {str(matchResult)}")
                _id = URIRef(matchResult.match.id)
            else:
                logging.error(f"Reconciliation failed for {keydesc} - {str(matchResult)}")
                if not skip_placeholders:
                    rs = ResourceSpec(_PROXY_CONCEPT_SPEC | {"name" : name})
                    reconcile_spec = {"key" : key, "keytype" : _type or str(SKOS.Concept)}
                    _id =  _create_resource(reconcile_spec, state, rs)
                    if not _id:
                        raise ValueError(f"Failed to create reconciled resource for {keydesc}")
                    else:
                        for pm in matchResult.possible_matches:
                            pm.record_as_rdf(state.current_graph(), _id)
            if not _id:
                raise ValueError(f"Failed to create reconciled resource for {keydesc}")
            else:
                record = ReconciliationRecord(key, _type, _id)
                record.result = matchResult
                state.record_reconcile_request(record)
        else:
            raise ValueError(f"Reconciliation attempt on {key}-{_type} at {api} returned empty result list")
    return _id

def _make_hash(key: str) -> str:
    _hash = hashlib.sha1()
    _hash.update(bytes(str(key),"UTF-8"))
    return base64.b32hexencode(_hash.digest()).decode("UTF-8")

_AUTO_CONCEPT_HASH_SPEC = {
    "name" : "autoCVhash",
    "properties" : {
        "@id" : "<hash({label})>",
        "@type" : "<skos:Concept>",
        "<skos:prefLabel>" : "{label}",
        "<skos:inScheme>" : "<{schemeID}>",
        "<skos:topConceptOf>": "<{schemeID}>",
        "^<skos:hasTopConcept>" : "<{schemeID}>",
    }
}

_AUTO_CONCEPT_SPEC = ResourceSpec({
    "name" : "autoCVlabel",
    "properties" : {
        "@id" : "<{id}>",
        "@type" : "<skos:Concept>",
        "<skos:prefLabel>" : "{label}",
        "<skos:inScheme>" : "<{schemeID}>",
        "<skos:topConceptOf>": "<{schemeID}>",
        "^<skos:hasTopConcept>" : "<{schemeID}>",
    }
})

_AUTO_CONCEPT_SCHEME_SPEC = ResourceSpec({
    "name" : "autoCVscheme",
    "properties" : {
        "@id" : "<{id}>",
        "@type" : "<skos:ConceptScheme>",
        "<dct:title>" : "{name}",
        "<dct:description>" : "Automatically generated concept scheme {name}"
    }
})

def autoCV(label: str, state: TemplateState, cv_name: str, cv_type: str | None = None) -> IdentifiedNode | None:
    """Generate a skos concept, and associated scheme, for the given level or reuse one we did earlier."""
    if not  label or len(label) == 0:
        return None
    _id = state.get_auto_entry(cv_name, label)
    if not _id:
        if not cv_name:
            cv_name = state.get("$prop") # type: ignore - know that $prop is set
        # Need to create concept, check concept scheme
        base = state.get('$datasetBase') + "/def/" + cv_name # type: ignore - know that $datasetBase is set
        schemeID = state.get_auto_entry(cv_name + "_", "scheme")
        if not schemeID:
            schemeID = _create_resource({"name" : cv_name, "id" : base + "_scheme"}, state, _AUTO_CONCEPT_SCHEME_SPEC)
            if not schemeID:
                raise ValueError(f"Failed to create scheme for {cv_name}")
            else:
                state.record_auto_cv(cv_name +"_", "scheme", schemeID)
        idstr = base + "/" + (_make_hash(label ) if cv_type == "hash" else normalize(label))
        _id = _create_resource({"label" : label, "schemeID" : schemeID, "id": idstr}, state, _AUTO_CONCEPT_SPEC)
        if not _id:
            raise ValueError(f"Failed to create concept for {cv_name} - {label}")
        else:
            state.record_auto_cv(cv_name, label, _id)
    return _id

def now(_: Any, state: TemplateState) -> Literal:
    return Literal(datetime.datetime.now().isoformat(), datatype=XSD.dateTime)
