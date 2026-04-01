# Literal Resources

## Introduction

This document outlines a proposal to add support for literal resource specifications to the rdf-mapper syntax.
A literal resource specification shares some of the features of a resource specification - in particular it
supports a conditional execution of the mapping.

## Option 1 - wrapper around existing pattern functionality

A resource specification is an object with the following keys:

| Key | Purpose |
| --- | ------- |
| `requires` | A dictionary for specifying the required values of properties for the resource specification to be executed. |
| `unless` | A dictionary for specifying the prohibited values of properties for the resource specification to be executed. |
| `pattern` | The literal value pattern for the resource. |

## Option 2 - more JSON-LD-like approach

A resource specification is an object with the following keys:

| Key | Purpose |
| --- | ------- |
| `requires` | A dictionary for specifying the required values of properties for the resource specification to be executed. |
| `unless` | A dictionary for specifying the prohibited values of properties for the resource specification to be executed. |
| `@value` | The value pattern for the value of the literal node. |
| `@type` | The data-type of the generated literal node. |
| `@language` | The language tag of the generated literal node. |

In this option, the `@value`, `@type` and `@language` could go under a `properties` key in the same way as a
non-literal resources template. If `@value` is present in a `properties` dictionary, only `@type` and `@language`
would be allowed, and the presence any other properties should result in an error.

## Decision

Decided to go with option 1 as this gives a clearer distinction between literal specifications and resource specifications and the existing pattern language supports specifying data-type and language directly in the pattern string.
