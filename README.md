# CASE Implementation: ExifTool

This implementation maps the RDF output of [ExifTool](https://exiftool.org/) into [CASE](https://caseontology.org/).


## Disclaimer

Participation by NIST in the creation of the documentation of mentioned software is not intended to imply a recommendation or endorsement by the National Institute of Standards and Technology, nor is it intended to imply that any specific software is necessarily the best available for the purpose.


## Usage

To install this software, clone this repository, and run `python3 setup.py install` from within this directory.  (You might want to do this in a virtual environment.)

The tests build several examples of mapped ExifTool output.  For instance, a sample analysis of a [govdocs1](https://digitalcorpora.org/corpora/files) file is [here](tests/govdocs1/files/799/987/analysis.json).  The [tests](tests/) directory demonstrates the expected usage patterns of ExifTool that this project analyzes.

Of note, ExifTool is expected to be run twice, to take advantage of some of the mapped information.  Both run types use these flags:

* `-binary`
* `-duplicates`
* `-xmlFormat`

Then, one run, the "Raw" run, is expected to use this flag:

* `--printConv` (Note the double dash)

You can see the expected command line forms in [this Makefile](tests/govdocs1/files/799/987/Makefile), observing the recipes for `799987_printConv.xml` and `799987_raw.xml`.  Note that ExifTool by default does not put the top `@rdf:about` into an IRI form, which causes some RDF processing libraries to reject ingesting the output.  Hence, one necessary postprocessing step is to translate the `@rdf:about` attribute into an IRI.  (This was done for the tests directory with a `sed` command.)


## Development status

This repository follows [CASE community guidance on describing development status](https://caseontology.org/resources/github_policies.html#development-statuses), by adherence to noted support requirements.

The status of this repository is:

4 - Beta


### Mapping status

A future feature of this repository will be a listing of this code base's coverage of ExifTool's RDF namespaces.  For now, the set of predicates found from analyzing the JPEG files of the govdocs1 corpus is listed [here](tests/govdocs1/predicates_discovered.txt).

Any concepts from ExifTool's RDF output that are not mapped in this code base are preserved by attaching to the CASE output.  See e.g. all of the namespaced concepts starting with the prefix `exiftool-` in [this example output file](tests/govdocs1/files/799/987/analysis.json).


#### Unstable representations

To assist with review of location representations, the property [`locn:geometry`](https://www.w3.org/ns/locn#locn:geometry) is sometimes used to map EXIF geolocation information.  At the time of initial implementation, this RDF term was under the status "testing," and supported Literal and Object references.  The end user should assume the usage of `locn:geometry`, and any concepts linked by it, are *deprecated* in this code base, with no guarantee of future support or availability.  Removal of these futures will not be considered reason to issue a (SEMVER) major-version release.


## Versioning

This project follows [SEMVER 2.0.0](https://semver.org/) where versions are declared.


## Ontology versions supported

This repository supports the CASE and UCO ontology versions that are linked as submodules in the [CASE Examples QC](https://github.com/ajnelson-nist/CASE-Examples-QC) repository.  Currently, those are:

* CASE 0.2.0
* UCO 0.4.0

Classes and properties are tested for vocabulary conformance.


## Repository locations

This repository is available at the following locations:
* [https://github.com/casework/CASE-Implementation-ExifTool](https://github.com/casework/CASE-Implementation-ExifTool)
* [https://github.com/usnistgov/CASE-Implementation-ExifTool](https://github.com/usnistgov/CASE-Implementation-ExifTool) (a mirror)

Releases and issue tracking will be handled at the [casework location](https://github.com/casework/CASE-Implementation-ExifTool).


## Make targets

Some `make` targets are defined for this repository:
* `all` - No effect.
* `check` - Run unit tests.  *NOTE*: The tests entail downloading some software to assist with formatting and conversion, from PyPI and from a [third party](https://github.com/edmcouncil/rdf-toolkit).  `make download` retrieves these files.
* `clean` - Remove test build files, but not downloaded files or the `tests/venv` virtual environment.
* `distclean` - Run `make clean` and further delete downloaded files and the `tests/venv` virtual environment.  Neither `clean` nor `distclean` will remove downloaded submodules.
* `download` - Download files sufficiently to run the unit tests offline.  This will *not* include the ontology repositories tracked as submodules.  Note if you do need to work offline, be aware touching the `setup.py` file in the root, or `tests/requirements.txt`, will trigger a virtual environment rebuild.

Note that downloading known sample binary data (JPEG files) is not yet done for unit testing, but might be done in the future.


### Operating system environments

This repository is tested in several POSIX environments.  See the [dependencies/](dependencies/) directory for package-installation and -configuration scripts for some of the test environments.

Note that running tests in FreeBSD requires running `gmake`, not `make`.
