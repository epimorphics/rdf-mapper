# Mapper Spec to represent the mapping to be applied
# TODO needs much more validation of the supplied template

from __future__ import annotations

from enum import Enum, StrEnum
import importlib.util
import os
import sys
from collections import ChainMap
from typing import Any, NoReturn, TextIO, cast

import yaml

from pydantic import BaseModel, Field, model_validator

class ResourceModel(BaseModel):
    name: str
    comment: str | None = None
    requires: dict[str, Any] | None = None
    unless: dict[str, Any] | None = None
    guard: str | None = None
    graph: str | None = Field(default=None, alias="@graph")
    preserved_graph: bool = True
    graphAdd: str | None = Field(default=None, alias="@graphAdd")
    properties: list[dict[str, Any]] | dict[str, Any] = []
    pattern: str | None = None

    @model_validator(mode="after")
    def check_pattern_or_properties(self) -> ResourceModel:
        if self.pattern and self.properties:
            raise ValueError("Resource spec cannot have both pattern and properties")
        if not self.pattern and not self.properties:
            raise ValueError("Resource spec must have either pattern or properties")
        return self
    
    @model_validator(mode="after")
    def check_graph_and_graphAdd(self) -> ResourceModel:
        if self.graph and self.graphAdd:
            raise ValueError("Resource spec cannot have both @graph and @graphAdd")
        return self

class PropTypeEnum(StrEnum):
    Int = "Int"
    Decimal = "Decimal"
    Date = "Date"
    Datetime = "Datetime"
    DateOrDatetime = "DateOrDatetime"

class PropModel(BaseModel):
    name: str
    comment: str | None = None
    prop: str
    type: PropTypeEnum | None = None
    cls: str = Field(alias="class")
    required: bool = False
    reconciliationAPI: str | None = None
    reconciliationType: str | None = None
    reconciliationFilters: dict[str, str] = Field(default_factory=dict)

class MapperModel(BaseModel):
    globals: dict[str, Any] = {}
    namespaces: dict[str, str] = {}
    one_offs: list[ResourceModel] = []
    resources: list[ResourceModel] = []
    mappings: dict[str, dict[str, str]] = {}
    embedded: list[ResourceModel] = []
    properties: list[PropModel] = []
    imports: list[str] = []


class MapperSpec:
    builtins = {"$baseURI": "https://epimorphics.com/datasets/"}

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
        "org": "http://www.w3.org/ns/org#",
    }

    def __init__(self, spec: MapperModel | dict = MapperModel(), auto_declare: bool = True) -> None:
        if isinstance(spec, dict):
            model = MapperModel(**spec)
        else:
            model = spec
        self._model = model
        self.auto_declare = auto_declare
        self.globals = model.globals
        self.context: ChainMap[str, Any] = ChainMap(self.globals, self.builtins)
        self.namespaces: ChainMap[str, str] = ChainMap(model.namespaces, self.builtinNamespaces)
        self.one_offs : list[ResourceSpec] = [ResourceSpec(m) for m in model.one_offs]
        self._init_defaults()
        self.resources: list[ResourceSpec] = [ResourceSpec(m) for m in model.resources]
        self.mappings = model.mappings
        self.embedded_resources : dict[str, ResourceSpec] = {}
        for e in model.embedded:
            rs = ResourceSpec(e)
            self.embedded_resources[rs.name] = rs
        self.propertySpecs : dict[str, PropSpec] = {}
        for p in model.properties:
            ps = PropSpec(p)
            self.propertySpecs[ps.name] = ps
        self._load_imports()

    def _init_defaults(self) -> None:
        if not self.context.get("$datasetBase"):
            self.context["$datasetBase"] = f"{self.context.get('$baseURI')}{self.context.get('$datasetID')}"

    def _load_imports(self) -> None:
        """Load yaml or python imports into the spec in order given."""
        self.imports = {}
        imports = self._model.imports
        if not imports:
            return
        acc_module = MapperSpec(MapperModel())
        for module_name in imports:
            fpath = _find_file(module_name)
            if not fpath:
                _error(f"Failed to find module {module_name}")
            if module_name.endswith(".yaml"):
                module = load_template(open(fpath))
                self.imports["module_name"] = module
                acc_module = acc_module.merge(module)
            elif module_name.endswith(".py"):
                name = module_name.replace(".py", "")
                spec = importlib.util.spec_from_file_location(name, fpath)
                if spec:
                    module = importlib.util.module_from_spec(spec)
                    if spec.loader:
                        sys.modules[name] = module
                        spec.loader.exec_module(module)
                else:
                    _error(f"Failed to load module {module_name}")
            else:
                _error(f"Module {module_name} not a recognized type")
        merged = acc_module.merge(self)
        self.globals = merged.globals
        self.namespaces = merged.namespaces
        self.propertySpecs = merged.propertySpecs
        self.embedded_resources = merged.embedded_resources
        self.one_offs = merged.one_offs
        self.mappings = merged.mappings

    def merge(self, other: MapperSpec) -> MapperSpec:
        """Return a new mapper spec with other values merged into these values. We take precedence."""
        merged_ps = list((other.propertySpecs | self.propertySpecs).values())
        merged_es = list((other.embedded_resources | self.embedded_resources).values())
        merged_oo = self.one_offs + other.one_offs
        merged_mppings = other.mappings | self.mappings
        return MapperSpec(MapperModel(
                globals =  other.globals | self.globals,
                namespaces = dict(other.namespaces) | dict(self.namespaces),
                properties = [ps._model for ps in merged_ps],
                embedded = [es._model for es in merged_es],
                one_offs = [oo._model for oo in merged_oo],
                mappings = merged_mppings,
            )
        )


def _error(message: str) -> NoReturn:
    print(f"Badly formatted mapping spec: {message}", file=sys.stderr)
    sys.exit(1)


def _find_file(fname: str) -> str | None:
    """Search for a file in the current directory and its subdirectories."""
    for root, dirs, files in os.walk(os.getcwd()):
        if fname in files:
            return root + "/" + fname
    return None


def load_template(file: TextIO) -> MapperSpec:
    with file:
        return MapperSpec(MapperModel.model_validate(yaml.safe_load(file)))


class PropSpec:
    def __init__(self, model: PropModel) -> None:
        self._model = model
        self.name = model.name
        self.comment = model.comment
        self.prop = model.prop
        self.type = None
        ty = model.type
        if ty:
            if str(ty) in ["Int", "Decimal", "Date", "Datetime", "DateOrDatetime"]:
                self.type = str(ty)
            else:
                _error(f"Property type not recognised, was {model.type} for property {model.name}")
        self.cls = model.cls
        self.required = model.required or False
        self.reconciliationAPI = model.reconciliationAPI
        self.reconciliationType = model.reconciliationType
        filters = model.reconciliationFilters or {}
        self.reconciliationFilters = list(filters.items())

    def propValueTemplate(self, pattern: str) -> tuple[str, str]:
        if self.type and pattern.startswith("{") and pattern.endswith("}"):
            pattern = f"{{{pattern[1:-1]} | as{self.type}}}"
        elif self.reconciliationType or self.reconciliationFilters:
            args = [self.name, self.reconciliationType, self.reconciliationAPI, self.reconciliationFilters]
            argstr = ",".join([_as_arg(x) for x in args])
            pattern = f"{{{pattern[1:-1]} | reconcile({argstr})}}"
        return (self.prop, pattern)


def _as_arg(value: Any) -> str:
    if isinstance(value, str):
        return "'" + value + "'"
    else:
        # TODO - more cases to cover
        return str(value)


class ResourceSpec:
    def __init__(self, model: ResourceModel) -> None:
        props = model.properties
        self._model = model
        self.name = model.name
        self.graph = model.graph or model.graphAdd
        self.preserved_graph = model.graphAdd is not None
        self.properties = [] if model.pattern is not None else _listify(props)
        self.pattern = model.pattern
        self.requires = model.requires
        self.unless = model.unless
        self.guard = model.guard

    def find_prop_defn(self, name: str) -> str | None:
        return next((p[1] for p in self.properties if p[0] == name), None)


def _listify(props: Any) -> list:
    """Flatten set of property specs to a list of pairs.

    We allow the properties of a class to be defined as a dict
    or a list of simple dicts. The list from is necessary if
    the same property key needs to be repeated. This normalization
    step is done eagerly at set up time to simplify later traversals."""
    properties = []
    if isinstance(props, list):
        for d in props:
            _listify_dict(d, properties)
    elif isinstance(props, dict):
        _listify_dict(props, properties)
    else:
        raise ValueError(f"Expecting properties for resource to a list or dict but found {props}")
    return properties


def _listify_dict(d: dict, acc: list) -> None:
    for key, value in d.items():
        acc.append((key, value))
