#!/usr/bin/make -f

# This software was developed at the National Institute of Standards
# and Technology by employees of the Federal Government in the course
# of their official duties. Pursuant to title 17 Section 105 of the
# United States Code this software is not subject to copyright
# protection and is in the public domain. NIST assumes no
# responsibility whatsoever for its use by other parties, and makes
# no guarantees, expressed or implied, about its quality,
# reliability, or any other characteristic.
#
# We would appreciate acknowledgement if the software is used.

SHELL := /bin/bash

top_srcdir := $(shell cd ../../../../.. ; pwd)

qc_srcdir := $(top_srcdir)/dependencies/CASE-Examples-QC

tests_srcdir := $(top_srcdir)/tests

RDF_TOOLKIT_JAR := $(qc_srcdir)/lib/rdf-toolkit.jar

COMM ?= $(shell which gcomm 2>/dev/null || which comm)
ifeq ($(COMM),)
$(error comm not found)
endif

SORT ?= $(shell which gsort 2>/dev/null || which sort)
ifeq ($(SORT),)
$(error sort not found)
endif

all: \
  undefined_vocabulary.txt

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
	rm __$@
	mv _$@ $@


analysis.ttl: \
  $(tests_srcdir)/.venv.done.log \
  799987_printConv.xml \
  799987_raw.xml
	export DEMO_UUID_REQUESTING_NONRANDOM=NONRANDOM_REQUESTED \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_exiftool \
	      --output-format turtle \
	      --print-conv-xml 799987_printConv.xml \
	      --raw-xml 799987_raw.xml \
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
799987_printConv.xml:
	exiftool \
	  -binary \
	  -duplicates \
	  -xmlFormat \
	  ./799/799987.jpg \
	  | sed \
	    -e "s_rdf:Description rdf:about='./_rdf:Description rdf:about='http://example.org/kb/govdocs1/_" \
	    > _$@
	mv _$@ $@

# NOTE: Contrary to other tools where "--" is an enabling flag pattern, "--printConv" is the flag to turn printConv off.
# This recipe is provided in case one wishes to reproduce the XML from the original JPEG file.
# TODO Discuss hosting govdocs samples on files.caseontology.org.
799987_raw.xml:
	exiftool \
	  --printConv \
	  -binary \
	  -duplicates \
	  -xmlFormat \
	  ./799/799987.jpg \
	  | sed \
	    -e "s_rdf:Description rdf:about='./_rdf:Description rdf:about='http://example.org/kb/govdocs1/_" \
	    > _$@
	mv _$@ $@

check: \
  undefined_vocabulary.txt
	test ! -s undefined_vocabulary.txt \
	  || (echo "ERROR:tests/govdocs1/files/799/987/Makefile:The output in analysis.json has undefined CASE or UCO terms.  The first few are:" >&2 && head undefined_vocabulary.txt >&2 && exit 1)
	source $(top_srcdir)/tests/venv/bin/activate \
	  && pytest

clean:
	@rm -f \
	  analysis.json \
	  analysis.ttl \
	  undefined_vocabulary.txt

undefined_vocabulary.txt: \
  analysis.json \
  $(qc_srcdir)/src/vocabulary_used.py \
  $(qc_srcdir)/tests/ontology_vocabulary.txt
	source $(qc_srcdir)/venv/bin/activate \
	  && python3 $(qc_srcdir)/src/vocabulary_used.py \
	    $< \
	    > $@___
	grep ':' $@___ \
	  | egrep -v '(ns.exiftool.ca|opengis.net|schema.org|w3.org)' \
	    | grep -v '/kb/' \
	      > $@__
	rm $@___
	LC_ALL=C \
	  $(COMM) \
	    -13 \
	    $(qc_srcdir)/tests/ontology_vocabulary.txt \
	    <(LC_ALL=C $(SORT) $@__) \
	    > $@_
	rm $@__
	mv $@_ $@
