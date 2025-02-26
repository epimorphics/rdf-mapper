#!/bin/env python3
import argparse
import csv
import json
import logging
import os
import sys
from typing import TextIO

from lib.mapper_spec import load_template
from lib.template_processor import TemplateProcessor


def process_jsonlines(file:TextIO, processor:TemplateProcessor) -> None:
    with(file):
        for line in file:
            data = json.loads(line)
            processor.process_row(data)
    processor.finalize()

def process_csv(file:TextIO, processor:TemplateProcessor)  -> None:
    with(file):
        reader = csv.DictReader(file)
        for row in reader:
            processor.process_row(row)
    processor.finalize()

argparser = argparse.ArgumentParser(
    description='Transform and reconcile csv or jsonlines file based on a mapping template'
)
argparser.add_argument('template', nargs=1, type=argparse.FileType('r'))
argparser.add_argument('datafile', nargs=1, type=argparse.FileType('r'))
argparser.add_argument('outfile', nargs='?', type=argparse.FileType('w'), default=sys.stdout)

def main() -> None:
    args = argparser.parse_args()
    spec = load_template(args.template[0])
    datafile = args.datafile[0]

    filename, extension = os.path.splitext(datafile.name)
    processor = TemplateProcessor(spec, filename, args.outfile)
    if (extension == ".json" or extension == ".jsonlines"):
        process_jsonlines(datafile, processor)
    elif (extension == ".csv"):
        process_csv(datafile, processor)
    else:
        print(f"Did not recognise file type of {datafile.name}")

def _init_logging() -> None:
#    logging.basicConfig(filename='mapper.log', encoding='utf-8', level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
    h1 = logging.FileHandler("mapper.log")
    h1.setFormatter(formatter)
    h1.setLevel(logging.INFO)
    h2 = logging.StreamHandler(sys.stderr)
    h2.setFormatter(formatter)
    h2.addFilter(lambda record: record.levelno >= logging.ERROR)
    h2.setLevel(logging.ERROR)

    logger.addHandler(h1)
    logger.addHandler(h2)

if __name__ == "__main__":
    _init_logging()
    main()
