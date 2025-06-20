#!/usr/bin/make -f

# Portions of this file contributed by NIST are governed by the
# following statement:
#
# This software was developed at the National Institute of Standards
# and Technology by employees of the Federal Government in the course
# of their official duties. Pursuant to Title 17 Section 105 of the
# United States Code, this software is not subject to copyright
# protection within the United States. NIST assumes no responsibility
# whatsoever for its use by other parties, and makes no guarantees,
# expressed or implied, about its quality, reliability, or any other
# characteristic.
#
# We would appreciate acknowledgement if the software is used.

SHELL := /bin/bash

top_srcdir := $(shell cd ../../../../.. ; pwd)

tests_srcdir := $(top_srcdir)/tests

RDF_TOOLKIT_JAR := $(top_srcdir)/dependencies/CASE-Utilities-Python/dependencies/CASE/dependencies/UCO/lib/rdf-toolkit.jar

all: \
  analysis.json

analysis.json: \
  analysis.ttl \
  $(RDF_TOOLKIT_JAR) \
  $(tests_srcdir)/src/compact.py
	java -jar $(RDF_TOOLKIT_JAR) \
	  --infer-base-iri \
	  --inline-blank-nodes \
	  --source $< \
	  --source-format turtle \
	  --target __$@ \
	  --target-format json-ld
	source $(tests_srcdir)/venv/bin/activate \
	  && python3 $(tests_srcdir)/src/compact.py \
	    __$@ \
	    _$@
	source $(top_srcdir)/tests/venv/bin/activate \
	  && case_validate \
	    _$@
	rm __$@
	mv _$@ $@


analysis.ttl: \
  $(tests_srcdir)/.venv.done.log \
  $(top_srcdir)/case_exiftool/__init__.py \
  000015_printConv.xml \
  000015_raw.xml
	export CDO_DEMO_NONRANDOM_UUID_BASE=$(top_srcdir) \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_exiftool \
	      --output-format turtle \
	      --print-conv-xml 000015_printConv.xml \
	      --raw-xml 000015_raw.xml \
	      --use-deterministic-uuids \
	      __$@
	source $(top_srcdir)/tests/venv/bin/activate \
	  && case_validate \
	    __$@
	java -jar $(RDF_TOOLKIT_JAR) \
	  --infer-base-iri \
	  --inline-blank-nodes \
	  --source __$@ \
	  --source-format turtle \
	  --target _$@ \
	  --target-format turtle
	rm __$@
	mv _$@ $@

# This recipe is provided in case one wishes to reproduce the XML from the original JPEG file.
# TODO Discuss hosting govdocs samples on files.caseontology.org.
000015_printConv.xml:
	exiftool \
	  -binary \
	  -duplicates \
	  -xmlFormat \
	  ./000015.pdf \
	  | sed \
	    -e "s_rdf:Description rdf:about='./_rdf:Description rdf:about='http://example.org/kb/govdocs1/_" \
	    > _$@
	mv _$@ $@

# NOTE: Contrary to other tools where "--" is an enabling flag pattern, "--printConv" is the flag to turn printConv off.
# This recipe is provided in case one wishes to reproduce the XML from the original JPEG file.
# TODO Discuss hosting govdocs samples on files.caseontology.org.
000015_raw.xml:
	exiftool \
	  --printConv \
	  -binary \
	  -duplicates \
	  -xmlFormat \
	  ./000015.pdf \
	  | sed \
	    -e "s_rdf:Description rdf:about='./_rdf:Description rdf:about='http://example.org/kb/govdocs1/_" \
	    > _$@
	mv _$@ $@

check: \
  analysis.json
	source $(top_srcdir)/tests/venv/bin/activate \
	  && pytest

clean:
	@rm -f \
	  analysis.json \
	  analysis.ttl
