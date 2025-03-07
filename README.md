# Simple RDF mapping tool

## key features

* declarative mapping spec (in yaml) for easy replay
* built in default patterns (URIs etc) to simplify mapping process
* built in pipeline operators for higher level transformations
* reconciliation and auto-CV creation for handling reference data
* can import vocabulary modules so mapping can refer to those terms
* can import processing modules for custom parsing or transformations

## Changes

### Version 0.2.0

   * wrap as module `rdf_mapper` which defines a `mapper` CLI
   * fix issues with skipping property rows that reference missing source values
   * include namespace declarations in the generated ttl
   * make `asDate` treat a bare year as `yyyy-01-01`
   * add `expr()` transform to allow inline python expressions in value mappings

## Dev set up

Create virtual env and install dependencies:

    python3 -m venv venv
    . venv/bin/activate
    pip install .

    pip install rdf_mapper[dev]
    pip install -e .

Linting:

    ruff check [--fix]

VScode ruff plugin for interactive linting and type checking.

Check for package updates:

    pip install pip-tools
    pip-compile --upgrade pyproject.toml

## usage

    mapper template input [output]

Generates a `mapper.log` with record of actions and errors, errors also flagged to stderr.

See ./examples/hse/templates for example mapping templates (note that templates 6 and 7 there require a reconciliation service running).

## Documentation

See [docs](./doc/doc.md)

