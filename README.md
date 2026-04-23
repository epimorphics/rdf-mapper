# Simple RDF mapping tool

## key features

* declarative mapping spec (in yaml) for easy replay
* built in default patterns (URIs etc) to simplify mapping process
* option to automatically declare implicit vocabulary terms on the fly
* built in pipeline operators for higher level transformations
* reconciliation and auto-CV creation for handling reference data
* can import vocabulary modules so mapping can refer to those terms
* can import processing modules for custom parsing or transformations

## usage

```sh
    mapper [--auto-declare] [--format=turtle] template input [output]
```

Formats supported are `turtle` (default), `trig`, `nquads`, `update` and `delete`.

For the default format then the default graph is written out as `turtle`, if any of the templates target named graphs their output will be lost.

With `update` format then a Sparql Update script is generated which can be used to update an existing dataset. All resources with a `@graph` will be written to the corresponding graph, replacing any existing content (the script will `DROP SILENT` all such graphs before inserting new data). Existing graph data can be preserved by using the `@graphAdd` directive instead.

With `delete` format the data is transformed as normal but the output will be a Sparql Update script which will delete any `@graph`s and will delete the triples from any `@graphAdd` graphs. This allows a previous update to be removed instead of replaced.

> [!NOTE]
> Care must be taken when using `delete` format with templates that include `@graphAdd`. Any bNodes generated in such preserved graphs will not be removed. Furthermore, any matching triples that had already been in the graph prior to the previous `update` will be removed and thus lost.

If no output file is specified the transformed data will be written to stdout.

Non-fatal warnings will be logged to stderr and to `mapper.log`.

See ./examples/hse/templates for example mapping templates (note that templates 6 and 7 there require a reconciliation service running).

## Documentation

See [docs](./doc/doc.md)

## Changes

See [changelog](./CHANGELOG.md)

## Dev set up

Create virtual env and install dependencies:

```sh
    python3 -m venv .venv
    . .venv/bin/activate
    pip install .

    pip install .[dev]
    pip install -e .
```

Linting:

```sh
    ruff check [--fix]
```

VScode ruff plugin for interactive linting and type checking.

Check for package updates:

```sh
    pip install pip-tools
    pip-compile --upgrade pyproject.toml
```
