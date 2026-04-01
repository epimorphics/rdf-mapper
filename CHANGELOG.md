# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

This project is currently in pre-release and a new minor version increment MAY NOT be backwards compatible with the previous minor version. Breaking changes are marked as BREAKING in the descriptions below.

## [Unreleased]

## [0.2.5] - 2026-03-13

### Added

- Added support for resource templates that generate a literal. (#42)

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
