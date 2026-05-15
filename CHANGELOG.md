# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

This project is currently in pre-release and a new minor version increment MAY NOT be backwards compatible with the previous minor version. Breaking changes are marked as BREAKING in the descriptions below.

## Unreleased

## Changed

- Changed the handling of property value templates that generate a URI (i.e. ones that use `<` and `>` around them). In the case that the pattern between the angle brackets resulted in no values, the processor would add an automatically generated value. From this version, this behaviour is removed and if the pattern returns no values, no URIs will be generated.

## [0.3.4] - 2026-05-11

## Fixed

- Remove unnecessary stdout logging (#77)
- Fix problem with globals not being overridden on command line

## [0.3.3] - 2026-05-11

### New

- Added support for defining global variable values on the command-line with the `-g`/`--set-global` option.

### Fixed

- Fixed an issue where the handling of missing/empty string values in 0.3.x differed to the handling in 0.2.x. When a missing/empty string/None value is encountered while expanding a property template, no value will be emitted even if the template contains static strings or other variables that expand to non-empty values. (#68)

## [0.3.2] - 2026-04-30

### Fixed

- Fixed issue where a property mapping like "{foo}" would generate a single literal value like "['A', 'B' 'C']" if the value of `foo` was an array. The mapper now correctly returns a separate literal value for each item in the array.

## [0.3.1]

### Fixed

- Fixed issue where a property mapping like "{foo}@en" would generate a plain literal "@en" when there is no value for `foo`. (#62)
- Fixed issue where a compact uri in a property mapping (e.g. "{foo}<xsd:string>") would not be expanded to the appropriate datatype URI. (#61)

## [0.3.0]

### Changed

- BREAKING: The constructors for building `MapperSpec` instances and related instances such as `ResourceSpec` now take a Pydantic model instance rather than a Python dict. The `MapperSpec` constructor will still accept a dict, which will be used internally to initialise an instance of the model, but the other `*Spec` classes will only accept `*Model` instances.
- BREAKING: The function for registering extension functions is now `rdf_mapper.lib.function.regsiter` (was `rdf_mapper.lib.template_support.register_fn`)

### Added

- Added support for resource templates that generate a literal. (#42)
- Added new built-in `slug` function to convert strings to "slugs" that can be used in a IRI path segment.
- Added new built-in `smap_to` function to apply a template to a child object or list of objects without any inherited context properties.
- Updated `map_to` and `smap_to` functions to now include the object being mapped as an additional value in the context under the key `$this`
- Added new built-in `to_entries` that expands an object to a list of key/value pairs, represented as a list of objects with a `$key` and `$value` property.

### Fixed

- Embedded resources are now loaded from imported templates (#45)
- The results of a `split` or `splitComma` function in a template pipeline are now individually passed down to the following functions in the pipeline rather than being passed as an array. (#41)

## [0.2.5] - 2026-03-13

### Fixed

- Fix handling of multi-line values when the mapping template includes a data-type or language tag. (#37)

## Version 0.2.0
  
- wrap as module `rdf_mapper` which defines a `mapper` CLI
- fix issues with skipping property rows that reference missing source values
- include namespace declarations in the generated ttl
- make `asDate` treat a bare year as `yyyy-01-01`
- add `expr()` transform to allow inline python expressions in value mappings
- suppress auto create of properties, classes and resource types unless `--auto-declare` is set - avoids need to always have explicit `@type`
- support for value mapping tables (could extend to support CSV-based maps if desired)
- support for output to multiple graphs (`@graph` and `@graphAdd`)
- support for Sparql Update output for multi-graph templates with `update` and `delete` format
- add hash transform for more flexible URI generation
