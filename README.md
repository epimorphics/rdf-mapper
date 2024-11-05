# Proof of Concept mapping tool

## key features

* declarative mapping spec (in yaml) for easy replay
* could imagine UI tool that incrementally generates the yaml
* built in default patterns (URIs etc) to simplify mapping process
* built in pipeline operators for higher level transformations
* reconciliation, auto-CV creation, intelligent date parse
* can import vocabulary modules so mapping can refer to those terms
* mapping between OWL and yaml representations TBD
* can import processing modules for custom parsing or transformations
* mapping specification should be enough to generate basic API configuration TBD

## usage

    ./mapper.py template input [output]

Generates a `mapper.log` with record of actions and errors, errors also flagged to stderr.

See ./templates for example mapping templates.

Templates 6 and 7 require reconciliation service running.

## Documentation

See [docs](./doc.md)

