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
import traceback
import uuid
from collections.abc import Callable, Mapping
from itertools import chain
from typing import Any, ChainMap, List, Union
from urllib.parse import urljoin

import dateparser
from rdflib import RDF, SKOS, XSD, BNode, IdentifiedNode, Literal, Node, URIRef, term
from rdflib.term import Identifier

from rdf_mapper.lib.mapper_spec import PropSpec, ResourceSpec
from rdf_mapper.lib.reconcile import MatchResult, ReconcileRequest, requestReconcile
from rdf_mapper.lib.template_state import ReconciliationRecord, TemplateState
from rdf_mapper.lib.pattern import Pattern
from rdf_mapper.lib.function import register
from rdf_mapper.lib.errors import MissingValueWarning

_VARPATTERN = re.compile(r"{([^}]*)}")

# def pattern_expand(template: str, state: TemplateState) -> str:
#     """Return template with var references {var} expanded from the given dict-like context.

#        Allows pattern to include a chain of transforms {var | fn | fn2}.
#        If the var references are embedded "foo{var}bar" the var will be converted to str.
#        If the whole pattern is a var reference "{var}" can return a typed value if the
#        context or any transformation functions return a typed value.
#     """
#     pattern = Pattern(template)
#     values = list(pattern.execute(state))
#     if _VARPATTERN.fullmatch(template):
#         return valueof_var(template[1:-1], state)
#     else:
#         last_match = 0
#         fragments = []
#         for m in _VARPATTERN.finditer(template):
#             prior = template[last_match:m.start()]
#             fragments.append(prior)
#             last_match = m.end()
#             varname = m.group()[1:-1]
#             val = valueof_var(varname, state)
#             if val:
#                 fragments.append(str(val))
#             else:
#                 fragments.append(m.group())
#         fragments.append(template[last_match:])
#         return ''.join(fragments)

# _PIPEPATTERN = re.compile(r"\s*\|\s*")

# def valueof_var(var: str, state: TemplateState) -> Any:
#     """Return the value of the var from the context.

#        Supports "var | fn | fn" syntax for normalisation and processing of the value.
#     """
#     varname, *chain = _PIPEPATTERN.split(var)
#     val = state.get(varname.strip())
#     if isinstance(val, str):
#         val = val.strip()
#     for fnname in chain:
#         fn = find_fn(fnname)
#         if fn:
#             if isinstance(val, list):
#                 result = []
#                 for i, v in enumerate(val):
#                     result.append(fn(v, state.child({"$listIndex": i})))
#                 val = result
#             else:
#                 val = fn(val, state)
#         else:
#             raise ValueError(f"Could not find function {fnname}")
#     if val is None or val == "":
#         raise MissingValueWarning(f"Could not find value {varname}")
#     return val

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

def pattern_expand(template: str, state: TemplateState) -> List[str]:
    """Expand a pattern to a string, applying any variable substitutions and function chains."""
    pattern = Pattern(template)
    return list(map(lambda lit: lit.value if isinstance(lit, Literal) else str(lit), filter(lambda v: v is not None, pattern.execute(state))))

def uri_expand(pattern: str, namespaces: Mapping[str,str], state: TemplateState) -> List[str]:
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
            urirefs = [str(uuid.uuid4())]
        elif uriref == "row":
            row = state.get('$row')
            if row:
                uriref = normalize(state.get('$file')) + "-" + str(row) # type: ignore
                if state.get('$listIndex') is not None:
                    # if nested resources in some list scan then need to include list index in generated resource ID
                    uriref = str(state.get('$listIndex')) + "/" + uriref
                urirefs = [uriref]
            else:
                urirefs = []
        elif uriref == "parent":
            parent = state.get("$parentID")
            if parent:
                uriref = parent + "/" + state.get("$resourceID") # type: ignore - know that $resourceID is set
                if state.get('$listIndex') is not None:
                    uriref = uriref + "/" + str(state.get('$listIndex'))
                urirefs = [uriref]
            else:
                urirefs = []
        elif _HASH_PATTERN.fullmatch(uriref):
            params = _HASH_PATTERN.fullmatch(uriref).group(1) # type: ignore
            params = _COMMA_SPLIT.split(params)
            _hash = hashlib.sha1()
            for p in params:
                if p.startswith("'") and p.endswith("'"):
                    _hash.update(bytes(p[1:-1],"UTF-8"))
                else:
                    _hash.update(bytes(str(state.get(p)),"UTF-8"))
            urirefs = [base64.b32hexencode(_hash.digest()).decode("UTF-8")]
        else:
            uri_values = pattern_expand(uriref, state)
            urirefs = []
            for uri_value in uri_values:
                urirefs.append(_expand_curi(str(uri_value), namespaces))

        if len(urirefs) == 0:
            urirefs.append(f"{state.get('$datasetBase')}/data/{state.get('$resourceID')}")

        return list(map(lambda uriref: urljoin(f"{state.get('$datasetBase')}/data/{state.get('$resourceID')}/", uriref) if not _URI_PATTERN.fullmatch(uriref) else uriref, urirefs)) # type: ignore - know that $datasetBase and $resourceID are set
    else:
        # Simple string, create as def in dataset namespace
        _id = f"{state.get('$datasetBase')}/def/{normalize(pattern)}"
        if state.spec.auto_declare:
            _record_implicit_prop(pattern, _id, None, state)
        return [_id]

def _expand_curi(uriref: str, namespaces: Mapping[str,str]) -> str:
    match = _CURI_PATTERN.fullmatch(uriref)
    if match:
        ns = namespaces.get(match.group(1))
        if ns:
            return ns + match.group(2)
    return uriref

_DT_PATTERN = re.compile(r"^(.+)\^\^(<[^>]+>)$", re.DOTALL)

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
            return list(map(lambda uriref: URIRef(uriref), uri_expand(pattern, namespaces, state)))
    else:
        p = Pattern(pattern)
        return list(p.execute(state))


def process_resource_spec(name: str, rs: ResourceSpec, state: TemplateState) -> term.Identifier | None:
    """Process a single resource specification in the current context."""
    state.add_to_context("$resourceID", name)
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
                logging.warning(
                    f"Skipping resource {rs.name} on row {state.get('$row')} because value for {key} is an empty string.")
                return None

    # If the resource spec has an unless dict, check the row for non-matching values
    if rs.unless:
        for key in rs.unless:
            value = state.get(key)
            if type(value) is str and value.strip() == "":
                # Treat empty columns / empty string values as undefined values for the purpose of unless
                value = None
            unless_value = rs.unless.get(key)
            if unless_value is None and value is not None:
                logging.warning(
                    f"Skipping resource {rs.name} on row {state.get('$row')} because value for {key} is not empty."
                )
                return None
            elif type(unless_value) is list:
                if value in unless_value:
                    logging.warning(
                        f"Skipping resource {rs.name} on row {state.get('$row')} because value for {key} ({value}) is "
                        f"one of the filtered values {unless_value}."
                    )
                    return None
            elif unless_value is not None and value == unless_value:
                logging.warning(
                    f"Skipping resource {rs.name} on row {state.get('$row')} because value for {key} is {value}."
                )
                return None

    if 'pattern' in rs.spec:
        pattern = rs.pattern
        if not isinstance(pattern, str):
            raise ValueError(f"Resource spec pattern must be a string, was {pattern}")
        expanded = value_expand(pattern, namespaces, state)
        if isinstance(expanded, list):
            logging.warning(f"Resource spec pattern {rs.name} expansion resulted in a list, only using first value")
            return expanded[0]
        else:
            return expanded

    # Check for switch of graph
    if rs.graph:
        graph = uri_expand(rs.graph, namespaces, state)[0]
        state = state.switch_to_graph(graph, rs.preserved_graph)

    # If we have no URI assignment default to the row pattern
    id_template = rs.find_prop_defn("@id") or "<row>"
    if id_template == "<_>":
        resource = BNode()
    else:
        _id =uri_expand(id_template, namespaces, state)[0]
        resource = URIRef(_id)
    state.backlinks[name] = resource
    state.add_to_context("$parentID", str(resource))

    # Use an assigned type or default
    type_template = rs.find_prop_defn("@type")
    if not type_template and state.spec.auto_declare:
        type_template = "<{$datasetBase}/def/{$resourceID}>"
        _id = uri_expand(type_template, namespaces, state)[0]
        _record_implicit_class(name, _id, rs.spec.get("comment"), state)
        type_uri = URIRef(_id)
        state.add_to_graph((resource, RDF.type, type_uri))
    elif type_template:
        type_uri = URIRef(uri_expand(type_template, namespaces, state)[0])
        state.add_to_graph((resource, RDF.type, type_uri))

    # Process the properties
    for (prop, template) in rs.properties:
        try:
            process_property_value(resource, prop, template, state)
        except MissingValueWarning as warn:
            logging.warning(f"Skipping {prop} on row {state.get('$row')}: {warn}")
        except ValueError as ex:
            if prop != "<rdfs:comment>":
                # The rdfs:comment guard is a kludge to reduce noise when auto declaring properties and classes
                if state.abort_on_error:
                    raise ValueError(f"Failed to process property {prop} on row {state.get('$row')}: {ex}") from ex
                else:
                    logging.warning(f"Skipping {prop} on row {state.get('$row')} because {ex}")
        except Exception as err:
            print(f"Unexpected error processing property {prop} on row {state.get('$row')}")
            print(traceback.format_exc())
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
            except MissingValueWarning as warn:
                logging.warning(f"Skipping {prop} on row {state.get('$row')}: {warn}")
            except ValueError as ex:
                if state.abort_on_error:
                    raise ValueError(f"Failed to process property {prop} on row {state.get('$row')}: {ex}") from ex
                else:
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
                class_ref = URIRef(uri_expand(prop_spec.cls, namespaces, state)[0])
                state.add_to_graph((resource, RDF.type, class_ref))
        else:
            raise ValueError(f"could not find property specification {prop}")

    propref = URIRef(uri_expand(prop, namespaces, state)[0])
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
            state.add_to_graph((v, propref, resource) if inverse else (resource, propref, v))
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

def _create_resource(data: dict, state: TemplateState, rs: ResourceSpec) -> term.Identifier | None:
    if not rs.name:
        raise ValueError("Resource spec must have a name, {rs}")
    return process_resource_spec(rs.name, rs, state.child(data))

def map_to(data: Any, state: TemplateState, rsname: str) -> List[Identifier | None]:
    if not data:
        return [None]
    if isinstance(data, list):
        return list(chain(map_to(d, state.child({"$listIndex": ix}), rsname)[0] for ix, d in enumerate(data)))  # type: ignore - TODO better typing for single depth list
    rs = state.spec.embedded_resources.get(rsname)
    if not rs:
            raise ValueError(f"map_to could not find embedded template called {rsname}")
    if not isinstance(data, dict):
        raise ValueError(f"map_to expecting data to be a dict but found {data}")
    return [_create_resource(data, state, rs)]

register("map_to", map_to)

def smap_to(data: Any, state: TemplateState, rsname: str) -> List[Identifier | None]:
    if not data:
        return [None]
    if isinstance(data, list):
        return list(chain(smap_to(d, state, rsname)[0] for ix, d in enumerate(data)))  # type: ignore - TODO better typing for single depth list
    rs = state.spec.embedded_resources.get(rsname)
    local_state = state.with_context({})
    if not rs:
            raise ValueError(f"smap_to could not find embedded template called {rsname}")
    if not isinstance(data, dict):
        raise ValueError(f"smap_to expecting data to be a dict but found {data}")
    return [_create_resource(data, local_state, rs)]

register("smap_to", smap_to)

def map_by(data: Any, state: TemplateState, mapping_name: str) -> Identifier | list[Identifier] | None:
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
    return value

register("map_by", map_by)

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
                    if not isinstance(_id, URIRef):
                        raise ValueError(f"Reconciled resource for {keydesc} is not a URIRef, got {_id}")
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

register("reconcile", reconcile)

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
            elif not isinstance(schemeID, IdentifiedNode):
                raise ValueError(f"Scheme ID for {cv_name} is not a URIRef or Blank Node, got {schemeID}")
            else:
                state.record_auto_cv(cv_name +"_", "scheme", schemeID)
        idstr = base + "/" + (_make_hash(label ) if cv_type == "hash" else normalize(label))
        _id = _create_resource({"label" : label, "schemeID" : schemeID, "id": idstr}, state, _AUTO_CONCEPT_SPEC)
        if not _id:
            raise ValueError(f"Failed to create concept for {cv_name} - {label}")
        elif not isinstance(_id, IdentifiedNode):
            raise ValueError(f"Concept ID for {cv_name} - {label} is not a URIRef or Blank Node, got {_id}")
        else:
            state.record_auto_cv(cv_name, label, _id)
    return _id

register("autoCV", autoCV)

