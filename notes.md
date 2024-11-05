# Mapper experiments

## Goals

High level, succinct, specification of ingest transforms - expressive in yaml.

Could be created by GUI tooling or knowledgeable user without necessarily deep python skills.

Build in conventions and processes to streamline specifications for simple cases. Minimal spec is just a name. Default id creation and URI patterns.

Load reusable plugin modules which can provide:
  - micro parsing
  - reusable ontology components
  - reconciliation (controlled scheme, reconciler address, property to use)
  - data patterns providing ones offs, collection patterns, namespace etc
  
Some support for data clean up but serious cleanup and validation should be separate part of the toolchain

Build on more flexible, lower level templating which experienced user can revert to.

Can handle tree structured (json) input as well as CSVs.

## Mapping specific

Mapping consists of:
   * modules to import
   * namespaces
   * global var settings (metadata, base id, etc)
   * transforms - list of preprocessing transforms to apply
   * list of properties - opened modules can supply properties with annotations, can update in template
   * list of oneOff resources to generate - opened modules can provide oneOff templates
   * list of resources to generate for each row (can be singleton, if empty defaults to standard pattern)

Globals:
   * datasetID - short "slug", unique to this data set, mandatory
   * baseURI - defaults to Agrimetrics built in default 
   * creator - email or other ID for the creator
   * description - textual description of the dataset
   * title - human readable label for the dataset

Modules:
   * there's a search path for modules so just need to give local name
   * foo.yaml modules define any element of mapping but updated by mapping def
   * foo.py modules include processing elements (transforms) and can also include equivalent of .yaml module

Property spec:
   * URI/Curi for the property
   * literal and expected type or set of types, will be checked and coerced
   * default cleaning (e.g. trim for strings, optional rounding for decimals)
   * or resource with expected type
   * required/optional - row will be skipped if required can't be generated
   * reconciliation target - API, type constraint, list of other filters available

   prop: uri-pattern
   type: string, date, datetime, int, decimal
   required: true
   reconcile: TBD

Resource:
   name: ""   - used for cross reference
   properties: 
     - prop-bindings
   
Property bindings:
   prop-name : value-pattern

prop-name:
   * "simplename" - turned into a property in the dataset def namespace
   * ":prop-spec-name" - use defined or imported property spec which gives URI
   * "<uri-pattern>" 
   * "^<uri-pattern>" - assert inverse reference
   * "@id" - id of the resource
   * "@type" - alt to rdf:type

URI patterns:
   * "name" - turned into a property in the dataset def namespace
   * "<namespace:prop>" - deference namespace to baseURI
   * "<foo{bar}>" - constructed URI using patterns that can reference any environment variable, if not absolute resolve related to data namespace
   * "<uuid>" - special case, generate a UUID for each row and use in dataset pattern
   * "<row>" - special case, generate an id for each row based on row number, file name and dataset pattern
   * "<parent>" - special case for embedded resources to generate URI relative to parent resource
   * "<::resource-name>" - cross reference to resource name
   * "<hash(col,...col)>" special case generate an id based on has of the cols of the given name

value-pattern:
   * "foo{bar}" - literal with optional variable substitution
   * "" - use prop-name as variable name, just transposing across
   * "<uri-pattern>" - reference URI resource 
   * { "pattern" : "value-pattern", ...}  - inline prop-spec overrides any corresponding prop-spec in force

If prop-name is a propspec then type coercion or reconciliation is performed according to the spec
If literals, after substitution look like foo@lan or foo^type then create land or typed literals
If pattern yields list then prop is repeated for each element of list

Patterns:
   * "{var}"  - substitute var from env, if not present omit prop, or abort entry depending on prop config
   * "{ var | transform | transform }" - apply transform chain, includes transform chain from prop spec
   * "{% arb python %}" - maybe
   
Transforms
   * type conversion: asInt, asDecimal, asDate, asDatetime, asDateOrDatetime
   * reconciliation: reconcile(api, types, other filters)  - arg list can include {var} substitutions
   * arb python functions defined in modules
   * possibly %...arb python...%

Global transforms
   * returns a dict of replacement or extra props 
     e.g. parse({col-name})
          parse(grammar-ref, {col-name})


# Futures

* auto collection type?
* higher performance version with more aggressive precompiling
* conditionals in value patterns ?: 
* embedded python in value patterns?
* Support dotted notation for deeper structure parse.
* Auto generate sapi-nt config from mapping spec?
* support turtle embedding in imports
* support shacl or other constraint expresssions imports
* Reusable components should be derivable from rdfs/owl
* subclass semantics (note imported classes on backlinks, add subclass in class generation)

Ontology fragments link props to classes? So if use prop carries expectation or constraints on needing other props to be consistent.
