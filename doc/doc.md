# Mapping tool

N.B. This is a proof-of-concept level tool only and not production ready.

## Overview

Maps are expressed in (largely) declarative yaml and the mapper tool will process a CSV or jsonlines file generating turtle output.

Operation:
```
    ./mapper.py [--auto-declare] template input [output]
```

If no output file is specified the transformed data will be written to stdout.

Non-fatal warnings will be logging to stderr and to `mapper.log`.

Key features: 

* builtin default patterns (URIs etc) to simplify the mapping process for normal use and enforce standard practice, while allowing for URI and value templating for experts
* builtin pipeline operators for higher level transformations, including transformers such as "intelligent" date parse and normalisation, allowing common cases to be handled without programming or regular expression bashing
* support for reconciliation to controlled vocabularies, with a builtin automatic pattern for handling reconciliation failures
* optionally include declarations of classes and properties referenced in the template, and declare implicit type for created resources, this is now off by default
* option to auto-create micro controlled vocabularies on the fly
* ability to import import vocabulary modules so that mapping can refer to those terms, supporting a minimal approach to ontology reuse
* ability to import processing modules when complex input parsing is required, allowing such coding tasks to be separated from the overall mapping definition

The mapper works by evaluating a set of templates in the the mapping file, which define the resources to emit, against each row of the supplied data. The field values from the row are passed to the mapping process as a `context` dict which will also include additional builtin and defined variables which can be used in the templates.

## Map file Structure

A full mapping file includes to following option al top level stanzas:

| Name | Description |
|---|---|
| `globals:` |  set of name/value bindings to add to the list variables passed in the processing context. |
| `namespaces:` | set of prefixes/URI maps which can be used as additional namespaces in the templates. |
| `imports:` | a list of file names to import, these may be python files defining additional transformers or functions, or yaml files defining reusable ontology modules |
| `resources:` | a list of named resource templates which will be instantiated for each row in the data. |
| `one_offs:` | a list of named resource templates which will be instances once for the mapper run (and so cannot include any per-row variable references) |
| `embedded:` | a list of named resource templates which can be used to map embedded structure within a row to a separate resource, used when parsing a complex string yields a structured value. |
| `properties:` | a list of named property definitions that can be referenced in resource templates. These can include type information (which supports automatic type coercion), reconciliation specifications as well as definitional information (label, comment, cardinality, range) |
| `class:` | a list of named class definitions, typically used in imported ontology modules. Provides a guide to mapping users on expected properties and will be emitted in the output as an inline class definition. |

The imported modules may have other placeholder fields (`ontology_source`, `constraints`) which are placeholders for future expansion and are currently ignored.

## Minimal example

A minimum template example is:

```
globals:
  $datasetID: hse

resources:  
  - name: HSERegistration
    properties:
      "Product Name:": ""
      "MAPP (Reg.) Number:":  ""
```

To process any dataset we need one piece of configuration information - a short identifier for the dataset. This is set by binding `$datasetID` in the first stanza. Variables use a convention of a `$` prefix for builtin or global configuration values.

This example resource definition means that each row of the source data will generate a resource of type `def:HSERegistration` with two properties, derived from the columns `Product Name:` and `MAPP (Reg.) Number:`. The punctuation like the trailing `:` is part of the source data and will be removed in generated the RDF property name to ensure we have a legal name. The output will also include a minimal class definition for `def:HSERegistration` and for the two properties. The resources themselves will be generated in a `data:` namespace. The `def:` and `data:` namespaces default to be relative to a dataset namespace which in turn uses the `$datasetID` combined with a default global base namespace.

A template can include multiple resource definitions so a row of data can generate multiple (linked) entities.

## Resource definitions

Resource definitions can have the following fields:

| Field | Description |
|---|---|
| `name` | Short name for the resource. For locally typed resources will be used the local name of the class URI and its `rdfs:label`. Also used for back references within templates. Required. |
| `comment` | Descriptive comment, will be used as `rdfs:comment` on any auto generated class definition. |
| `requires` | An optional dictionary mapping column names to the value required to be in that column for the resource mapping to be applied. If no value is provided, then the column is required to have any non-empty value.
| `properties` | List of property/value templates defining the properties to attach to the generated resource |

Entries in `one_offs` are identical to `resources` definitions, the difference is in their application, one offs are only generated once for the run and are a way to create static resources that the rows can refer to. 

When the property/value definitions are processed then missing variables referenced in the template will cause that property to be skipped but will not abort the resource or the whole role. In this way templates can safely refer to optional values in the source data. Use the `requires` guard noted above if the entire resources _should_ be skipped if some source values are missing. When property values or resources are skipped this fact is recorded in the `mapping.log` file (or standard error if logging has not been configured) to help with debugging unexpectedly missing values.

## Patterns

The values which will be bound to properties (or used to generate the URI or type of a resource via `@id` and `@type`) are defined by templates.

### URI patterns

URI templates (which generate URI values) are mostly indicated by surrounding `<..>` markers. The supported templates are shown below.

| URI Template | Interpretation |
|---|---|
| `<http://example.com/{x}>` | Templated URI, any variables in `{...}` are replaced by the corresponding value from context |
| `<prefix:local>` | A CURI, where `prefix` is a builtin or locally defined namespace and `local` gives a localname component which can include templated variables |
| `<row>` | Generate a URI in the dataset data namespace based on the file name and row number |
| `<uuid>` | Generate a URI in the dataset data namespace base on a UUID |
| `<hash(col1,...,coln)>`| Generate a URI in the dataset data namespace based encoded hash of the values of the given columns |
| `<parent>` | Generate a URI relative to the parent URI when processing an embedded template, the relative URI will use the resourceID and any list index if the embedded template is processing a list of values |
| `<::name>` | Back reference to the URI of a previously generated resource with the given name |
| `name` | Generate a URI in the dataset data namespace with localname `name`, this version, without `<...>` is only applicable in cases where the template is known to be a URI (`@id` or `@type`) |
| `<_>` | Generate a blank node rather than a URI node. |

Base URIs for the data set default to `<{$datasetBase}/data/>` for data elements and `<{$datasetBase}/def/>` for ontology elements.  Where `$datasetBase` defaults to `{$baseURI}{$datasetId}`.

Namespaces used as prefixes in CURIs can be defined in the namespaces stanza, e.g.

```
namespaces:
  voc : https://epimorphics.com/def/
```

Namespaces for `rdf`, `rdfs`, `owl`, `skos`, `skosxl`, `dct`, `qb` and `org` are builtin and don't need to be declared.

### Literal patterns

In addition to URI values then plain and typed literal templates are available:

| Value template | Interpretation |
|---|---|
| `foo{x}bar` | Plain template, any variables in `{...}` are replaced by the corresponding value from context |
| "" | Empty string indicates using the property name as variable name, just transposing across, so equivalent to `{$prop}` where `$prop` is the property reference |
| `foo{x}bar@lang` | Language typed literal |
| `foo{x}bar^^<uri>` | Data typed literal. The value `<uri>` is expanded as a URI pattern. |
| `{var \| fn \| fn}` | The value of the variable is transformed via a pipeline of transformation operators such as type conversion |

### Variables

Variables available for use in patterns include the fields (columns) each data row and the following:

| Value | Description |
|---|---|
| `$baseURI` | base of URI for all data and definitions, defaults to `https://epimorphics.com/datasets/` |
| `$datasetID` | short id string for this dataset, must be set in the template |
| `$file` | name of the file being ingested |
| `$row` | row number of the line being ingested |
| `$prop` | name of the current property being expanded |
| `$datasetBase` | base URI for this dataset, defaults to `{$baseURI}{$datasetId}` |
| `$resourceID` | short ID for the resource being generated, uses the name field in the template |
| `$parentID`  | full URI for parent resource when processing embedded templates |
| `$listIndex` |index in list when processing a list of results from a chained transform |
| `$reconciliationAPI` | API endpoint for reconciliation, may be global or for a specific property |

### Property references

The properties defined for a resource are a map from a property specification to a value template or a list of value templates where the value template can be either a URI pattern or a literal pattern as above.

A property specification may also be mapped to a resource specification. In this case, the inner resource specification is processed and the URI of the resulting resource is used as the property value.

The property specification can be:

| Property spec | Description |
|---|---|
| `name` | A property placed in the `def` namespace of the dataset |
| `:name` | A reference to a named property defined in a properties stanza (possibly in an import) |
| `<uri-pattern>` | An explicitly defined URI using any of the URI pattern options |
| `^<uri-pattern>` | Inverted reference which instead of linking from the resource being templated to its value, it links from the value (assumed to be a URI) to this resource |
| `@id` | Pattern for the URI to give the resource, defaults to `<row>` |
| `@type` | Pattern for `rdf:type` for the resource, defaults to resource name (as a dataset-relative URI) |

## Properties

It is possible to define properties in the `properties` stanza, either in the main template or in imports. Such property definitions both generate ontology axioms and can trigger additional processing when referencing the property.

Fields in a property specification are:

| Field | Description |
|---|---|
| `name` | A short name for the property, required |
| `prop` | URI pattern for the property |
| `required` | Boolean, set to false for optional properties |
| `type` | A type for the property. This will cause a type transformer called `asType` to be run where `Type` is the value of the `type` field |
| `range` | Range declaration for the property |
| `reconciliationFilters` | Indicates the property values should reconciled against a defined reconciliation API using the filters defined here |

For example, if we have declaration:

```
properties:
  - name:  authorisationDate
    prop:  "<agvoc:authorisationDate>"
    type:  "Date"
```

And a reference in the template of:

```
resources:  
  - name: HSERegistration
    properties:
      ":authorisationDate"     : "{First Authorisation Date:}"
```

So the property reference `:authorisationDate` references the named entry in the `properties` list. It means that each row will be assigned a property whose URI is given in the property specification, i.e. `agvoc:authorisationDate` and whose value is taken from the source column `First Authorisation Date:` and then transformed with the `asDate` transformer.

If that column is missing no property value is assigned.

## Transformers

A variable binding within a value pattern can be passed through a set of transformation functions to normalize them before adding to the data. The builtin transformers are:

| Transformer | Description  |
|---|------------------------|
| `asInt` | Coerce value to an `xsd:integer` (or omit if it can't be coerced)  |
| `asDecimal` | Coerce value to an `xsd:decimal` (or omit if it can't be coerced)   |
| `asBoolean` | Treat "yes", "true", "ok" and "1" as `true^^xsd:boolean` and all else as `false^^xsd:boolean`. The string match is case-insensitive.  |
| `asBoolean(...)` | Treat each of the values passed as arguments as `true^^xsd:boolean` and all else as `false^^xsd:boolean`. The string match is case-insensitive.  |              
| `asDate` | Try to parse as an `xsd:date` using an intelligent guess at the format, omit if can't be parsed, treats for numbers that look like years represent as Jan 1st of that year  |
| `asDateTime` | Try to parse as an `xsd:dateTime` using an intelligent guess at the format, omit if can't be parsed  |
| `asDateOrDatetime` | Try to parse as an `xsd:date` or `xsd:datetime` using an intelligent guess at the format, omit if can't be parsed   |
| `trim` | Remove leading and trailing white space (applied by default but can be useful in pipelines)    |
| `splitComma` | Transform to a list of values splitting at "," characters    |
| `split('xx')` | Transform to a list of values splitting at occurrences of the string "xx"   |
| `expr('...')` | Evaluate a python expression with `x` bound to the incoming variable e.g. `{value | expr('x*3+2')}` |
| `map_to('template')` | Assumes the variable is an object or list of objects (e.g. as generated by a parser) and transforms to a resource or set of resources using the embedded template named `template`   |
| `reconcile(...)` | Reconcile the value, see later    |
| `autoCV` or `autoCV(name,type)` | Replace a string value with a generated concept whose preLabel is the string value. Will emit the autogenerated concept scheme. If no `name` is given then it uses the name of the property being generated as the name of the concept scheme. The optional `type` argument can be either `hash` to use a hash of the label as the local part of the concept URI or `label` to use the normalized label directly (the default). |
| `now` | Return the current date time, the argument is ignored so use as e.g. `{\|now}  |

New transformations can be defined as python functions and registered with the mapper. The function should accept an incoming value and a `rdf_mapper.lib.template_state.TemplateState` and be register using `rdf_mapper.lib.template_support.register_fn`, see parser examples.

When a transform generates a list of values (e.g. the `split` transformers) then the property will be repeated for each value after processing. A more complex transformer such as parser might generate a nested object or a list of nest objects which can then be handled using `map_to`. 

## Reconciliation

Reconciliation uses an API (as specified by the W3C Entity Resolution community group) to look up a value string in a set of controlled vocabularies and return the URI for the matching concept. If there is no confident match then optionally a placeholder concept will be generated with the candidate matches and match confidence recorded as annotations of the placeholder.

While the reconciliation is implemented as a transformer it is more convenient to specify it as an attribute of the property whose value is being transformed. For example:

```
properties:
  - name: crop
    prop: "<agvoc:crop>"
    reconciliationFilters: 
      "skos:inScheme" : "https://data.agrimetrics.co.uk/crop-definition/CropDefinitionScheme"

embedded:
  - name: CropSituation
    properties:
      "@id"       : "<parent>"
      ":crop"      : "{crop}"      
```

Here the `:crop` property in `CropSituation` is defined in the properties stanza with a reconciliation filter.

The list of filters are each property/value pairs which can be used to filter the set of candidates to consider. Theses will typically limit the match to a particular concept scheme (as the above) or to a particular type. Though any property which might be present on the concepts to match can be used in the filter.

In the case of filtering to a specific type there is a convenience shortcut `reconciliationType`.

The API endpoint is normally defined as a global variable to that it can be reused across multiple reconciled properties:

```
globals:
  $reconciliationAPI: http://localhost:8888/api/reconcile
```

However, it is also possible to define it directly on the property definition using the `reconciliationAPI` attribute.

So a fuller example might be:

```
properties:
  - name: crop
    prop: "<agvoc:crop>"
    reconciliationType: "https://data.agrimetrics.co.uk/crop-definition/CropDefinition"
    reconciliationAPI: "http://localhost:8888/api/reconcile"
    reconciliationFilters: 
       prop: value
```

## Importing

It is possible to import files which are either additional templates specifications in a yaml file or definitions of additional transformation functions in python. The former are used to access resuable ontology fragments and the latter for handling special cases of data such as parsers for embedded micro-formats.

```
imports:
  - registrations.yaml
  - crop-parser.py
```

## Logging and errors

Missing property values are not treated as a errors, the corresponding property is simply omitted.

Attempts at type coercion which fail are similarly treated as if missing rather than emitting unexpected types. No warning is current flagged for these cases which is probably not right.

All significant actions, such as reconciliation attempts and results are logged to a `mapper.log` file. Errors are _also_ logged to stderr.

## Limitations

`subclassOf` and `subpropertyOf` are not implemented when extending imported ontology modules.

Templates are not properly validated so misspelled directives may be silently ignored and missing or ill-formatted expected elements may generate mysterious errors messages.

Parsing of arguments and python fragments in transformers is fragile and should be replaced by a full grammar and lark parser.

Lacks support for non-flat source json, though the embedded templates used to handle micro-parsing give a foundation for this.

The `class` stanza is inconsistently named, should be `classes:`.
