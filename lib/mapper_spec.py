# Mapper Spec to represent the mapping to be applied
# TODO needs much more validation of the supplied template

from __future__ import annotations
from collections import ChainMap
import sys
import os
import yaml
import importlib.util
    
class MapperSpec:
    builtins = {
        "$baseURI" : "https://epimorphics.com/datasets/"
    }

    builtinNamespaces = {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "owl": "http://www.w3.org/2002/07/owl#",
        "skos": "http://www.w3.org/2004/02/skos/core#",
        "skosxl": "http://www.w3.org/2008/05/skos-xl#",
        "dct": "http://purl.org/dc/terms/",
        "foaf": "http://xmlns.com/foaf/0.1/",
        "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
        "qb": "http://purl.org/linked-data/cube#",
        "vcard": "http://www.w3.org/2006/vcard/ns#",
        "org": "http://www.w3.org/ns/org#"
    }

    def __init__(self, spec: dict = {}) -> None:
        self.spec = spec
        self.globals = self._getAsDict('globals')
        self.context = ChainMap(self.globals, self.builtins)
        self.namespaces = ChainMap(self._getAsDict('namespaces'), self.builtinNamespaces)
        self.one_offs = [ResourceSpec(spec) for spec in self._getAsList('one_offs')]
        self._init_defaults()
        self.resources = [ResourceSpec(spec) for spec in self._getAsList('resources')]
        self.embedded_resources = {}
        for e in self._getAsList('embedded'):
            rs = ResourceSpec(e)
            self.embedded_resources[rs.name] = rs
        self.propertySpecs = {}
        for p in self._getAsList("properties"):
            ps = PropSpec(p)
            self.propertySpecs[ps.name] = ps
        self._load_imports()

    def _init_defaults(self):
        if not self.context.get('$datasetBase'):
            self.context['$datasetBase'] = f"{self.context.get('$baseURI')}{self.context.get('$datasetID')}"

    def _load_imports(self):
        """Load yaml or python imports into the spec in order given."""
        self.imports = {}
        if not self.spec.get("imports"): 
            return
        acc_module = MapperSpec({})
        for module_name in self.spec.get("imports"):
            fpath = _find_file(module_name)
            if not fpath: 
                _error(f"Failed to find module {module_name}")
            if module_name.endswith(".yaml"):
                module = load_template(open(fpath))
                self.imports['module_name'] = module
                acc_module = acc_module.merge(module)
            elif module_name.endswith(".py"):
                name = module_name.replace(".py","")
                spec = importlib.util.spec_from_file_location(name, fpath)
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
            else:
                _error(f"Module {module_name} not a recognized type")
        merged = acc_module.merge(self)
        self.globals = merged.globals
        self.namespaces = merged.namespaces
        self.propertySpecs = merged.propertySpecs
        self.one_offs = merged.one_offs
        
    def _getAsDict(self, field: str) -> dict:
        v = self.spec.get(field)
        if (v is None):
            return {}
        elif (type(v) is dict):
            return v
        else:
            _error(f'Expected {field} to be a map/dict was {v}')

    def _getAsList(self, field: str) -> list:
        v = self.spec.get(field)
        if (v is None):
            return []
        elif (type(v) is list):
            return v
        else:
            _error(f'Expected {field} to be a list was {v}')

    def merge(self, other: MapperSpec) -> MapperSpec:
        """Return a new mapper spec with other values merged into these values. We take precedence."""
        merged_ps = list((other.propertySpecs | self.propertySpecs).values())
        merged_es = list((other.embedded_resources | self.embedded_resources).values())
        merged_oo = self.one_offs + other.one_offs
        return MapperSpec({
            "globals" : other.globals | self.globals,
            "namespaces" : dict(other.namespaces) | dict(self.namespaces),
            "properties" : [ps.spec for ps in merged_ps],
            "embedded" : [es.spec for es in merged_es],
            "one_offs": [oo.spec for oo in merged_oo]
        })

def _error(message:str):
    print(f'Badly formatted mapping spec: {message}', file=sys.stderr)
    sys.exit(1)

def _find_file(fname: str) -> str:
    for root, dirs, files in os.walk(os.getcwd()):
        if fname in files:
            return (root + "/" + fname)
    return None
  
def load_template(file) -> MapperSpec:
    with(file):
        return MapperSpec(yaml.safe_load(file))
          
class PropSpec:
    def __init__(self, spec: dict) -> None:
        if isinstance(spec, dict) and "name" in spec and "prop" in spec:
            self.spec = spec
            self.name = spec.get("name")
            self.prop = spec.get("prop")
            self.type = None
            type = spec.get("type")
            if type:
                if type in ["Int", "Decimal", "Date", "Datetime", "DateOrDatetime"]:
                    self.type = type
                else:
                    _error(f"Property type not recognised, was {self.type}")
            self.cls = spec.get("class")
            self.required = spec.get("required") or False
            self.reconciliationAPI = spec.get("reconciliationAPI")
            self.reconciliationType = spec.get("reconciliationType")
            filters = spec.get("reconciliationFilters") or {}
            self.reconciliationFilters = list(filters.items())
        else:
            _error(f"Property spec must be a map with at least name and prop, was {spec}")

    def propValueTemplate(self, pattern: str) -> tuple[str, str]:
        if self.type and pattern.startswith("{") and pattern.endswith("}"):
            pattern = f"{{{pattern[1:-1]} | as{self.type}}}"
        elif self.reconciliationType or self.reconciliationFilters:
            args = [self.name, self.reconciliationType, self.reconciliationAPI, self.reconciliationFilters]
            argstr = ",".join([ _as_arg(x) for x in args])
            pattern = f"{{{pattern[1:-1]} | reconcile({argstr})}}"
        return (self.prop, pattern)

def _as_arg(value) -> str:
    if isinstance(value, str):
        return "'" + value + "'"
    else:
        # TODO - more cases to cover
        return str(value)
    
class ResourceSpec:
    def __init__(self, spec: dict) -> None:
        if isinstance(spec, dict) and "name" in spec and "properties" in spec:
            self.spec = spec
            self.name = spec.get("name")
            self.properties = _listify(spec.get("properties"))
            self.requires = spec.get("requires")
            if self.requires is not None and not isinstance(self.requires, dict):
                _error(f"Resource spec requires must be a dictionary, was {self.requires}")
        else:
            _error(f"Resource spec must be a map with at least name and some properties, was {spec}")

    def find_prop_defn(self, name: str) -> str:
        return next((p[1] for p in self.properties if p[0] == name), None)

def _listify(props) -> list:
    """Flatten set of property specs to a list of pairs.
    
       We allow the properties of a class to be defined as a dict
       or a list of simple dicts. The list from is necessary if
       the same property key needs to be repeated. This normalization 
       step is done eagerly at set up time to simplify later traversals."""
    properties = []
    if isinstance(props, list):
        for d in props: _listify_dict(d, properties)
    elif isinstance(props, dict):
        _listify_dict(props, properties)
    else:
        raise ValueError(f"Expecting properties for resource to a list or dict but found {props}")
    return properties
    
def _listify_dict(d: dict, acc: list):
    for key, value in d.items():
        acc.append((key, value))
