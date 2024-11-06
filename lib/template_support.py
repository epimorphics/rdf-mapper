"""
    Functions implementing all the mechanisms of template expansion and substitution.

    Primary entry point is process_resource_spec, though some of the machinery such as 
    pattern_expand and uri_expand may be usable in other contexts.

    Built in processing functions and registration of externally defined functions
    are also implemented here since they need access parts of this machinery.
"""

import sys
import re
from rdflib import Literal, XSD, URIRef, term, RDF, SKOS
import uuid
import hashlib
import base64
from urllib.parse import urljoin
import dateparser
import datetime
from lib.template_state import TemplateState, ReconciliationRecord
from lib.mapper_spec import ResourceSpec, PropSpec
from lib.reconcile import requestReconcile, MatchResult, ReconcileRequest
import logging

_VARPATTERN = re.compile("""{([^}]*)}""")

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

_PIPEPATTERN = re.compile("\s*\|\s*")

def valueof_var(var: str, state: TemplateState):
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
    return val

_POOR_URI_CHARS = re.compile("[^\w\-]+")

def normalize(s: str) -> str:
    norm = _POOR_URI_CHARS.sub("_",s.strip())
    if norm.endswith("_"): norm = norm[:-1]
    if norm.startswith("_"): norm = norm[1:]
    return norm

_CURI_PATTERN = re.compile("([_A-Za-z][\w\-\.]*):([\w\-\.]+)")
_URI_PATTERN = re.compile("(https?|file|urn)://.*")   # TODO Support other schemes
_HASH_PATTERN = re.compile("hash\s?\((.*)\)$")
_COMMA_SPLIT = re.compile("\s*,\s*")

def uri_expand(pattern: str, namespaces: dict, state: TemplateState) -> str:
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
                uriref = normalize(state.get('$file')) + "-" + str(row)
                if state.get('$listIndex') != None:
                    # if nested resources in some list scan then need to include list index in generated resource ID
                    uriref = str(state.get('$listIndex')) + "/" + uriref
            else:
                uriref = None
        elif uriref == "parent":
            parent = state.get("$parentID")
            if parent:
                uriref = parent + "/" + state.get("$resourceID")
                if state.get('$listIndex') != None:
                    uriref = uriref + "/" + str(state.get('$listIndex'))
            else:
                uriref = None
        elif _HASH_PATTERN.fullmatch(uriref):
            params = _HASH_PATTERN.fullmatch(uriref).group(1)
            params = _COMMA_SPLIT.split(params)
            hash = hashlib.sha1()
            for p in params:
                if p.startswith("'") and p.endswith("'"):
                    p = p[1:-1]
                hash.update(bytes(str(state.get(p)),"UTF-8"))
            uriref = base64.b32hexencode(hash.digest()).decode("UTF-8")
        else:
            uriref = pattern_expand(uriref, state.context)
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
        id = f"{state.get('$datasetBase')}/def/{normalize(pattern)}"
        _record_implicit_prop(pattern, id, None, state)
        return id

def _expand_curi(uriref: str, namespaces: dict,) -> str:
    match = _CURI_PATTERN.fullmatch(uriref)
    if match:
        ns = namespaces.get(match.group(1))
        if ns:
            return ns + match.group(2)
    return uriref

_LANGSTRING_PATTERN = re.compile("^(.+)@([\w\-]+)$")

def value_expand(pattern: str, namespaces: dict, state: TemplateState) -> term.Identifier:
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
    if pattern.startswith("<") and pattern.endswith(">"):
        if pattern.startswith("<::"):
            return state.backlinks.get(pattern[3:-1])
        else:
            return URIRef(uri_expand(pattern, namespaces, state))
    else:
        val = pattern_expand(pattern, state)
        return _value_to_rdf(val)
        
def _value_to_rdf(val) -> term.Identifier:
    if isinstance(val, term.Identifier):
        return val
    elif val == None:
        return None
    elif isinstance(val, list):
        return [_value_to_rdf(v) for v in val]
    elif isinstance(val, str):
        if _LANGSTRING_PATTERN.fullmatch(val):
            match = _LANGSTRING_PATTERN.fullmatch(val)
            return Literal(match.group(1), lang=match.group(2))
        else:
            return Literal(val)
    else:
        return Literal(val)

def process_resource_spec(name: str, rs: ResourceSpec, state: TemplateState) -> URIRef:
    """Process a single resource specification in the current context."""
    state.add_to_context("$resourceID", name)
    properties = rs.properties
    namespaces = state.spec.namespaces

    # If we have no URI assignment default to the row pattern
    id_template = rs.find_prop_defn("@id") or "<row>"
    id =uri_expand(id_template, namespaces, state)
    resource = URIRef(id)
    state.backlinks[name] = resource
    state.add_to_context("$parentID", id)

    # Use an assigned type or default
    type_template = rs.find_prop_defn("@type") 
    if not type_template:
        type_template = "<{$datasetBase}/def/classes/{$resourceID}>"
        id = uri_expand(type_template, namespaces, state)
        _record_implicit_class(name, id, rs.spec.get("comment"), state)
        type_uri = URIRef(id)
    else:
        type_uri = URIRef(uri_expand(type_template, namespaces, state))
    state.graph.add((resource, RDF.type, type_uri))
    for (prop, template) in rs.properties:
        try:
            process_property_value(resource, prop, template, state)
        except ValueError as ex:
            logging.error(f"Skipping {prop} on row {state.get('$row')} due to exception {ex}")
    return resource

def process_property_value(resource: URIRef, prop: str, template, state: TemplateState):
    """Process a single property expansion."""
    if prop == "@id" or prop == "@type":
        return   # already processed
    if isinstance(template, list):
        # Multiple expansions defined for this property
        for template_item in template:
            process_property_value(resource, prop, template_item, state)
        return
    inverse = prop.startswith("^")
    if inverse:
        prop = prop[1:]
    namespaces = state.spec.namespaces
    prop_spec = None
    if prop.startswith(":"):
        prop_spec: PropSpec = state.spec.propertySpecs.get(prop[1:])
        if prop_spec:
            (prop, template) = prop_spec.propValueTemplate(template)
            if prop_spec.cls:
                class_ref = URIRef(uri_expand(prop_spec.cls, namespaces, state))
                state.graph.add((resource, RDF.type, class_ref))
        else:
            raise ValueError(f"could not find property specification {prop}")
    propref = URIRef(uri_expand(prop, namespaces, state))
    propname = prop
    if prop_spec:
        _record_implicit_prop(prop_spec.name,  str(propref), prop_spec.spec.get("comment"), state)
        propname = prop_spec.name
    if isinstance(template, str):
        if template == "":
            template = "{" + prop + "}"
        try:
            value = value_expand(template, namespaces, state.child({"$prop": propname}))
        except ValueError as err:
            # Skip lines with no value to lookup, 
            logging.warn(f"Skipping property due to {err}")
            value = None
    else:
        raise NotImplementedError("Implement inline property specs")
    if isinstance(value, list):
        for v in value: 
            state.graph.add((resource, propref, v))
    else:
        if value != None:
            if inverse:
                triple = (value, propref, resource)
            else:
                triple = (resource, propref, value)
            state.graph.add(triple)
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

def _record_implicit_class(name: str, id: str, comment: str, state: TemplateState):
    if not state.record_auto_emit("class", name):
        _create_resource({"id" : id, "label": name, "comment": comment}, state, _AUTO_CLASS_SPEC)

_AUTO_PROP_SPEC = ResourceSpec({
    "name": "AUTO_PROP",
    "properties": {
        "@id" : "<{id}>",
        "@type" : "<rdf:Property>",
        "<rdfs:label>": "{label}",
        "<rdfs:comment>": "{comment}",
    }
})

def _record_implicit_prop(name: str, id: str, comment: str, state: TemplateState):
    if not state.record_auto_emit("prop", name):
        _create_resource({"id" : id, "label": name, "comment": comment}, state, _AUTO_PROP_SPEC)

# Built in transformation functions, provisional 

_FUN_REGISTRY = {}

def register_fn(name: str, fn):
    """Add a named function to the register of operation that can be used in var processing chains."""
    _FUN_REGISTRY[name] = fn

_CALL_PATTERN = re.compile("([\w]+)\s*\((.*)\)")

def find_fn(call: str):
    """
    Return the function corresponding to a function call spec.

    If the call is a simply a function name then look it up in globals or registry.
    If it looks like a call with argument then construct a matching lambda and register that.
    """
    fn = globals().get(call) or _FUN_REGISTRY.get(call)
    if not fn:
        match = _CALL_PATTERN.fullmatch(call)
        if match:
            dfn = f"lambda value, state: {match.group(1)}(value, state,{match.group(2)})"
            fn = eval(dfn)
            # print(f"Registering {dfn}")
            register_fn(call, fn)
    return fn

def asInt3(s: str, state: TemplateState = None):
    """Return triple integer value of string, used for testing."""
    return int(s)*3

def asInt(s: str, state: TemplateState = None) -> Literal:
    return Literal(s, datatype=XSD.integer) if s else None

def asDecimal(s: str, state: TemplateState = None) -> Literal:
    return Literal(s, datatype=XSD.decimal) if s else None

def asDateTime(s: str, state: TemplateState = None) -> Literal:
    dt = dateparser.parse(s)
    return Literal(dt.isoformat(), datatype=XSD.dateTime) if dt else None

def asDate(s: str, state: TemplateState = None) -> Literal:
    dt = dateparser.parse(s)
    return Literal(dt.date().isoformat(), datatype=XSD.date) if dt else None

def asDateOrDatetime(s: str, state: TemplateState = None) -> Literal:
    dt = dateparser.parse(s)
    if dt:
        if dt.time() == datetime.time(0,0):
            return Literal(dt.date().isoformat(), datatype=XSD.date)
        else:
            return Literal(dt.isoformat(), datatype=XSD.dateTime)
    else:
        return None

def asBoolean(s: str, state: TemplateState = None) -> Literal:
    return Literal(s.lower() in ["yes", "true", "ok", "1"], datatype=XSD.boolean)

def trim(s: str, state: TemplateState = None) -> str:
    return s.strip()

def splitComma(s: str, state: TemplateState = None) -> list:
    return _COMMA_SPLIT.split(s)

def split(s: str, state: TemplateState, reg: str) -> list:
    return re.split(reg, s)

def _create_resource(data: dict, state: TemplateState, rs: ResourceSpec) -> URIRef:
    return process_resource_spec(rs.name, rs, state.child(data))

def map_to(data: dict, state: TemplateState, rsname: str) -> URIRef:
    if not data:
        return None
    rs = state.spec.embedded_resources.get(rsname)
    if not rs: 
            raise ValueError(f"map_to could not find embedded template called {rsname}")
    if not isinstance(data, dict):
        raise ValueError(f"map_to expecting data to be a dict but found {data}")
    return _create_resource(data, state, rs)

_PROXY_CONCEPT_SPEC = {
    "properties" : {
        "@id" : "<hash(key,keytype)>",
        "@type" : "<{keytype}>",
        "<skos:prefLabel>" : "{key}"
    }
}

def reconcile(key: str, state: TemplateState, name: str, type: str = None, endpoint: str = None, filters: list = None, skip_placeholders: bool = False) -> URIRef:
    """Reconcile the key/type.
    
       name is used as local resource name if need to create a proxy.
       Assumes there's a reconciliationAPI key in the context.
       """
    id = state.reconciled_ref(key, type)
    if not id:
        # TODO batch up reconciliation requests, instead of on-the-fly
        api = endpoint or state.get("$reconciliationAPI")
        if not api:
            raise ValueError("No reconciliationAPI configured")
        namespaces = state.spec.namespaces
        if type:
            type = _expand_curi(type, namespaces)
        if filters:
            filters = [(_expand_curi(p, namespaces),_expand_curi(v, namespaces)) for p,v in filters]
        matches = requestReconcile(api, [ReconcileRequest(key, type, filters)])
        if len(matches) == 1:
            matchResult: MatchResult = matches[0]
            keydesc = f"{key}-{type}" if type else key
            if matchResult.match:
                logging.info(f"Reconciled {keydesc} to {str(matchResult)}")
                id = URIRef(matchResult.match.id)
            else:
                logging.error(f"Reconciliation failed for {keydesc} - {str(matchResult)}")
                if not skip_placeholders:
                    rs = ResourceSpec(_PROXY_CONCEPT_SPEC | {"name" : name})
                    reconcile_spec = {"key" : key, "keytype" : type or str(SKOS.Concept)}
                    id =  _create_resource(reconcile_spec, state, rs)
                    for pm in matchResult.possible_matches:
                        pm.record_as_rdf(state.graph, id)
            record = ReconciliationRecord(key, type, id)
            record.result = matchResult
            state.record_reconcile_request(record)
        else:
            raise ValueError(f"Reconciliation attempt on {key}-{type} at {api} returned empty result list")
    return id

def _make_hash(key: str) -> str:
    hash = hashlib.sha1()
    hash.update(bytes(str(key),"UTF-8"))
    return base64.b32hexencode(hash.digest()).decode("UTF-8")
        
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

def autoCV(label: str, state: TemplateState, cv_name: str = None, cv_type: str = None) -> URIRef:
    """Generate a skos concept, and associated scheme, for the given level or reuse one we did earlier."""
    id = state.get_auto_entry(cv_name, label)
    if not id:
        if not cv_name:
            cv_name = state.get("$prop")
        # Need to create concept, check concept scheme
        base = state.get('$datasetBase') + "/def/" + cv_name
        schemeID = state.get_auto_entry(cv_name + "_", "scheme")
        if not schemeID:
            schemeID = _create_resource({"name" : cv_name, "id" : base + "_scheme"}, state, _AUTO_CONCEPT_SCHEME_SPEC)
            state.record_auto_cv(cv_name +"_", "scheme", schemeID)
        idstr = base + "/" + (_make_hash(label ) if cv_type == "hash" else normalize(label))
        id = _create_resource({"label" : label, "schemeID" : schemeID, "id": idstr}, state, _AUTO_CONCEPT_SPEC)
        state.record_auto_cv(cv_name, label, id)
    return id

def now(ignore, state: TemplateState) -> Literal:
    return Literal(datetime.datetime.now().isoformat(), datatype=XSD.dateTime)
