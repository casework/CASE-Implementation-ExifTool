#!/usr/bin/env python3

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

"""
This tool parses the RDF output of ExifTool, mapping it into UCO properties and relationships-of-assumption.  An analyst should later annotate the output with their beliefs on its verity.
"""

__version__ = "0.11.0"

import argparse
import contextlib
import logging
import os
import typing

import case_utils.inherent_uuid
import cdo_local_uuid
import rdflib.plugins.sparql
import rdflib.util
from case_utils.namespace import (
    NS_RDF,
    NS_RDFS,
    NS_UCO_CORE,
    NS_UCO_IDENTITY,
    NS_UCO_LOCATION,
    NS_UCO_OBSERVABLE,
    NS_UCO_TYPES,
    NS_XSD,
)
from cdo_local_uuid import local_uuid

_logger = logging.getLogger(os.path.basename(__file__))

NS_DRAFTING = rdflib.Namespace("http://example.org/ontology/drafting/")
NS_EXIFTOOL_COMPOSITE = rdflib.Namespace("http://ns.exiftool.org/Composite/1.0/")
NS_EXIFTOOL_ET = rdflib.Namespace("http://ns.exiftool.org/1.0/")
NS_EXIFTOOL_EXIFTOOL = rdflib.Namespace("http://ns.exiftool.org/ExifTool/1.0/")
NS_EXIFTOOL_GPS = rdflib.Namespace("http://ns.exiftool.org/EXIF/GPS/1.0/")
NS_EXIFTOOL_SYSTEM = rdflib.Namespace("http://ns.exiftool.org/File/System/1.0/")
NS_EXIFTOOL_FILE = rdflib.Namespace("http://ns.exiftool.org/File/1.0/")
NS_EXIFTOOL_IFD0 = rdflib.Namespace("http://ns.exiftool.org/EXIF/IFD0/1.0/")
NS_EXIFTOOL_EXIFIFD = rdflib.Namespace("http://ns.exiftool.org/EXIF/ExifIFD/1.0/")
NS_EXIFTOOL_NIKON = rdflib.Namespace("http://ns.exiftool.org/MakerNotes/Nikon/1.0/")
NS_EXIFTOOL_PDF_PDF = rdflib.Namespace("http://ns.exiftool.org/PDF/PDF/1.0/")
NS_EXIFTOOL_PREVIEWIFD = rdflib.Namespace(
    "http://ns.exiftool.org/MakerNotes/PreviewIFD/1.0/"
)
NS_EXIFTOOL_INTEROPIFD = rdflib.Namespace("http://ns.exiftool.org/EXIF/InteropIFD/1.0/")
NS_EXIFTOOL_IFD1 = rdflib.Namespace("http://ns.exiftool.org/EXIF/IFD1/1.0/")

argument_parser = argparse.ArgumentParser(epilog=__doc__)
argument_parser.add_argument("--base-prefix", default="http://example.org/kb/")
argument_parser.add_argument("--debug", action="store_true")
argument_parser.add_argument(
    "--output-format", help="Override extension-based format guesser."
)
argument_parser.add_argument(
    "--print-conv-xml",
    help="A file recording the output of ExifTool run against some file.  Expects exiftool was run as for --raw-xml, but also with the flag --printConv (note the double-dash).",
)
argument_parser.add_argument(
    "--raw-xml",
    help="A file recording the output of ExifTool run against some file.  Expects exiftool was run with -binary, -duplicates, and -xmlFormat.",
    required=True,
)
argument_parser.add_argument(
    "--use-deterministic-uuids",
    action="store_true",
    help="Use UUIDs computed using the case_utils.inherent_uuid module.",
)
argument_parser.add_argument(
    "out_graph",
    help="A self-contained RDF graph file, in the format either requested by --output-format or guessed based on extension.",
)


def controlled_dictionary_object_to_node(
    graph: rdflib.Graph,
    ns_base: rdflib.Namespace,
    controlled_dict: typing.Dict[str, rdflib.Literal],
) -> rdflib.URIRef:
    n_controlled_dictionary = ns_base["ControlledDictionary-" + local_uuid()]
    graph.add((n_controlled_dictionary, NS_RDF.type, NS_UCO_TYPES.ControlledDictionary))
    for key in sorted(controlled_dict.keys()):
        v_value = controlled_dict[key]
        try:
            assert isinstance(v_value, rdflib.Literal)
        except AssertionError:
            _logger.info("v_value = %r." % v_value)
            raise
        n_entry = ns_base["ControlledDictionaryEntry-" + local_uuid()]
        graph.add((n_controlled_dictionary, NS_UCO_TYPES.entry, n_entry))
        graph.add((n_entry, NS_RDF.type, NS_UCO_TYPES.ControlledDictionaryEntry))
        graph.add((n_entry, NS_UCO_TYPES.key, rdflib.Literal(key)))
        graph.add((n_entry, NS_UCO_TYPES.value, v_value))
    return n_controlled_dictionary


def manufacturer_name_to_node(
    graph: rdflib.Graph,
    ns_base: rdflib.Namespace,
    *args: typing.Any,
    printconv_name: typing.Optional[str] = None,
    raw_name: typing.Optional[str] = None,
    **kwargs: typing.Any,
) -> typing.Optional[rdflib.URIRef]:
    """
    This method is provided to be overwritten in case a mapping function exists within the user's knowledge base.
    """
    n_manufacturer: typing.Optional[rdflib.URIRef] = None
    if printconv_name is not None or raw_name is not None:
        n_manufacturer = ns_base["Identity-" + local_uuid()]
        graph.add((n_manufacturer, NS_RDF.type, NS_UCO_IDENTITY.Identity))

    if printconv_name is not None:
        assert isinstance(n_manufacturer, rdflib.URIRef)
        graph.add((n_manufacturer, NS_UCO_CORE.name, rdflib.Literal(printconv_name)))
        if raw_name is not None:
            if printconv_name != raw_name:
                graph.add((n_manufacturer, NS_RDFS.comment, rdflib.Literal(raw_name)))
    elif raw_name is not None:
        assert isinstance(n_manufacturer, rdflib.URIRef)
        graph.add((n_manufacturer, NS_UCO_CORE.name, rdflib.Literal(raw_name)))
    return n_manufacturer


class ExifToolRDFMapper(object):
    """
    This class maps ExifTool RDF predicates into UCO objects and Facets.

    The implementation strategy is:
    * Iterating through an if-elif ladder of IRIs with known interpretation strategies; and
    * Lazily instantiating objects with class @property methods.
    The lazy (or just-in-time) instantiation is because some graph objects can be needed for various reasons, but because of ExifTool's varied format coverage, it would not be appropriate to create each object each time.  For instance, on encountering GPS data in a JPEG's EXIF data (prefixes "http://ns.exiftool.org/Composite/1.0/GPS", "http://ns.exiftool.org/EXIF/GPS/1.0/GPS"), three things need to be created:
    * A Location object.
    * A derivation and assumption relationship between the original trace and the inferred Location object.
    * Entries in the EXIF dictionary.
    Separately, other EXIF properties like picture dimension descriptors need the EXIF dictionary.  The first IRI found to need the dictionary will trigger its creation, leading to its serialization.

    Those interested in extending this tool's mapping coverage of ExifTool IRIs are encouraged to update the method map_raw_and_printconv_iri.
    """

    def __init__(
        self,
        graph: rdflib.Graph,
        ns_base: rdflib.Namespace,
        *args: typing.Any,
        use_deterministic_uuids: bool = False,
        **kwargs: typing.Any,
    ) -> None:
        assert isinstance(graph, rdflib.Graph)

        self._exif_dictionary_dict: typing.Optional[
            typing.Dict[str, rdflib.Literal]
        ] = None

        self._pdf_dictionary_dict: typing.Optional[typing.Dict[str, rdflib.Literal]] = (
            None
        )

        self._graph = graph

        self._use_deterministic_uuids = use_deterministic_uuids

        self._kv_dict_raw: typing.Dict[rdflib.URIRef, rdflib.term.Node] = dict()
        self._kv_dict_printconv: typing.Dict[rdflib.URIRef, rdflib.term.Node] = dict()
        self._mime_type: typing.Optional[str] = None
        self._n_camera_object: typing.Optional[rdflib.URIRef] = None
        self._n_camera_object_device_facet: typing.Optional[rdflib.URIRef] = None
        self._n_content_data_facet: typing.Optional[rdflib.URIRef] = None
        self._n_exif_dictionary_object: typing.Optional[rdflib.URIRef] = None
        self._n_exif_facet: typing.Optional[rdflib.URIRef] = None
        self._n_file_facet: typing.Optional[rdflib.URIRef] = None
        self._n_location_object: typing.Optional[rdflib.URIRef] = None
        self._n_pdf_dictionary_object: typing.Optional[rdflib.URIRef] = None
        self._n_pdf_file_facet: typing.Optional[rdflib.URIRef] = None
        self._n_location_object_latlong_facet: typing.Optional[rdflib.URIRef] = None
        self._n_observable_object: typing.Optional[rdflib.URIRef] = None
        self._n_raster_picture_facet: typing.Optional[rdflib.URIRef] = None
        self._n_relationship_object_location: typing.Optional[rdflib.URIRef] = None
        self._n_unix_file_permissions_facet: typing.Optional[rdflib.URIRef] = None
        self._oo_slug: str = "File-"
        self.ns_base = ns_base

    def map_raw_and_printconv_iri(self, n_exiftool_predicate: rdflib.URIRef) -> None:
        """
        This method implements mapping into UCO for known ExifTool IRIs.

        This method has a side effect of mutating the internal variables:
        * self._kv_dict_raw
        * self._kv_dict_raw
        * self._exiftool_predicate_iris
        """
        assert isinstance(n_exiftool_predicate, rdflib.URIRef)
        exiftool_iri = str(n_exiftool_predicate)

        if exiftool_iri == "http://ns.exiftool.org/Composite/1.0/GPSAltitude":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                l_altitude = rdflib.Literal(v_raw.toPython(), datatype=NS_XSD.decimal)
                self.graph.add(
                    (
                        self.n_location_object_latlong_facet,
                        NS_UCO_LOCATION.altitude,
                        l_altitude,
                    )
                )
        elif exiftool_iri == "http://ns.exiftool.org/Composite/1.0/GPSLatitude":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                l_latitude = rdflib.Literal(v_raw.toPython(), datatype=NS_XSD.decimal)
                self.graph.add(
                    (
                        self.n_location_object_latlong_facet,
                        NS_UCO_LOCATION.latitude,
                        l_latitude,
                    )
                )
        elif exiftool_iri == "http://ns.exiftool.org/Composite/1.0/GPSLongitude":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                l_longitude = rdflib.Literal(v_raw.toPython(), datatype=NS_XSD.decimal)
                self.graph.add(
                    (
                        self.n_location_object_latlong_facet,
                        NS_UCO_LOCATION.longitude,
                        l_longitude,
                    )
                )
        elif exiftool_iri == "http://ns.exiftool.org/Composite/1.0/GPSPosition":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_printconv, rdflib.Literal):
                self.graph.add((self.n_location_object, NS_RDFS.label, v_printconv))
        elif exiftool_iri == "http://ns.exiftool.org/EXIF/ExifIFD/1.0/ExifImageHeight":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                self.exif_dictionary_dict["Image Height"] = v_raw
                self.graph.add(
                    (
                        self.n_raster_picture_facet,
                        NS_UCO_OBSERVABLE.pictureHeight,
                        rdflib.Literal(int(v_raw.toPython())),
                    )
                )
        elif exiftool_iri == "http://ns.exiftool.org/EXIF/ExifIFD/1.0/ExifImageWidth":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                self.exif_dictionary_dict["Image Width"] = v_raw
                if self._n_raster_picture_facet is not None:
                    self.graph.add(
                        (
                            self.n_raster_picture_facet,
                            NS_UCO_OBSERVABLE.pictureWidth,
                            rdflib.Literal(int(v_raw.toPython())),
                        )
                    )
        elif exiftool_iri in {
            "http://ns.exiftool.org/EXIF/GPS/1.0/GPSAltitudeRef",
            "http://ns.exiftool.org/EXIF/GPS/1.0/GPSAltitude",
            "http://ns.exiftool.org/EXIF/GPS/1.0/GPSLatitudeRef",
            "http://ns.exiftool.org/EXIF/GPS/1.0/GPSLatitude",
            "http://ns.exiftool.org/EXIF/GPS/1.0/GPSLongitudeRef",
            "http://ns.exiftool.org/EXIF/GPS/1.0/GPSLongitude",
        }:
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                dict_key = exiftool_iri.replace(
                    "http://ns.exiftool.org/EXIF/GPS/1.0/GPS", ""
                )
                self.exif_dictionary_dict[dict_key] = v_raw
        elif exiftool_iri == "http://ns.exiftool.org/EXIF/IFD0/1.0/Make":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            printconv_str: typing.Optional[str] = None
            raw_str: typing.Optional[str] = None
            if isinstance(v_printconv, rdflib.Literal):
                printconv_str = str(v_printconv)
            if isinstance(v_raw, rdflib.Literal):
                raw_str = str(v_raw)
            n_manufacturer = manufacturer_name_to_node(
                self.graph, self.ns_base, printconv_name=printconv_str, raw_name=raw_str
            )
            if n_manufacturer is not None:
                self.graph.add(
                    (
                        self.n_camera_object_device_facet,
                        NS_UCO_OBSERVABLE.manufacturer,
                        n_manufacturer,
                    )
                )
        elif exiftool_iri == "http://ns.exiftool.org/EXIF/IFD0/1.0/Model":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                # TODO - If both values available and differ, map printconv to deviceType?
                self.graph.add(
                    (self.n_camera_object_device_facet, NS_UCO_OBSERVABLE.model, v_raw)
                )
        elif exiftool_iri == "http://ns.exiftool.org/File/1.0/MIMEType":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                self.mime_type = v_raw.toPython()
                # Special case - graph logic is delayed for this IRI, because of needing to initialize the base ObservableObject based on the value.
        elif exiftool_iri == "http://ns.exiftool.org/File/System/1.0/FileAccessDate":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                self.graph.add(
                    (
                        self.n_file_facet,
                        NS_UCO_OBSERVABLE.accessedTime,
                        rdflib.Literal(
                            v_raw.toPython().replace(" ", "T"), datatype=NS_XSD.dateTime
                        ),
                    )
                )
        elif (
            exiftool_iri == "http://ns.exiftool.org/File/System/1.0/FileInodeChangeDate"
        ):
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                self.graph.add(
                    (
                        self.n_file_facet,
                        NS_UCO_OBSERVABLE.metadataChangeTime,
                        rdflib.Literal(
                            v_raw.toPython().replace(" ", "T"), datatype=NS_XSD.dateTime
                        ),
                    )
                )
        elif exiftool_iri == "http://ns.exiftool.org/File/System/1.0/FileModifyDate":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                self.graph.add(
                    (
                        self.n_file_facet,
                        NS_UCO_OBSERVABLE.modifiedTime,
                        rdflib.Literal(
                            v_raw.toPython().replace(" ", "T"), datatype=NS_XSD.dateTime
                        ),
                    )
                )
        elif exiftool_iri == "http://ns.exiftool.org/File/System/1.0/FileName":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                self.graph.add((self.n_file_facet, NS_UCO_OBSERVABLE.fileName, v_raw))
        elif exiftool_iri == "http://ns.exiftool.org/File/System/1.0/FilePermissions":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                raw = v_raw.toPython()
                if raw.isdigit() and int(raw) < 1000:
                    # TODO - The permissions facets seem to need revision.
                    # No POSIX permission property exists.  extPermissions can be added to an ExtInodeFacet, but that facet is scoped to EXT file systems.
                    # It might be more appropriate to call a class POSIXFilePermissionsFacet rather than UNIXFilePermissionsFacet.
                    # Until this modeling is revised, the FilePermissions property will be consumed into comments.
                    # This issue is being tracked in this ticket: https://unifiedcyberontology.atlassian.net/browse/OC-117
                    self.graph.add(
                        (self.n_unix_file_permissions_facet, NS_RDFS.comment, v_raw)
                    )
            if isinstance(v_printconv, rdflib.Literal):
                self.graph.add(
                    (self.n_unix_file_permissions_facet, NS_RDFS.comment, v_printconv)
                )
        elif exiftool_iri == "http://ns.exiftool.org/File/System/1.0/FileSize":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                self.graph.add(
                    (
                        self.n_content_data_facet,
                        NS_UCO_OBSERVABLE.sizeInBytes,
                        rdflib.Literal(int(v_raw.toPython())),
                    )
                )
        elif exiftool_iri == "http://ns.exiftool.org/PDF/PDF/1.0/Author":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                self.pdf_dictionary_dict["Author"] = v_raw
                self.graph.add(
                    (
                        self.n_pdf_file_facet,
                        NS_DRAFTING.pdfAuthor,
                        rdflib.Literal(v_raw.toPython()),
                    )
                )
        elif exiftool_iri == "http://ns.exiftool.org/PDF/PDF/1.0/CreateDate":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                # CreationDate entry in self.pdf_dictionary_dict references term in ISO 32000-1:2008 PDF Table 317.
                self.pdf_dictionary_dict["CreationDate"] = v_raw
                self.graph.add(
                    (
                        self.n_pdf_file_facet,
                        NS_UCO_OBSERVABLE.pdfCreationDate,
                        rdflib.Literal(
                            v_raw.toPython().replace(" ", "T"), datatype=NS_XSD.dateTime
                        ),
                    )
                )
        elif exiftool_iri == "http://ns.exiftool.org/PDF/PDF/1.0/Creator":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                self.pdf_dictionary_dict["Creator"] = v_raw
                self.graph.add(
                    (
                        self.n_pdf_file_facet,
                        NS_DRAFTING.pdfCreator,
                        rdflib.Literal(v_raw.toPython()),
                    )
                )
        elif exiftool_iri == "http://ns.exiftool.org/PDF/PDF/1.0/Linearized":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                self.pdf_dictionary_dict["Linearized"] = v_raw
                self.graph.add(
                    (
                        self.n_pdf_file_facet,
                        NS_DRAFTING.pdfLinearized,
                        rdflib.Literal(v_raw.toPython()),
                    )
                )
        elif exiftool_iri == "http://ns.exiftool.org/PDF/PDF/1.0/ModifyDate":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                self.pdf_dictionary_dict["ModDate"] = v_raw
                self.graph.add(
                    (
                        self.n_pdf_file_facet,
                        NS_UCO_OBSERVABLE.pdfModDate,
                        rdflib.Literal(
                            v_raw.toPython().replace(" ", "T"), datatype=NS_XSD.dateTime
                        ),
                    )
                )
        elif exiftool_iri == "http://ns.exiftool.org/PDF/PDF/1.0/PDFVersion":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                self.pdf_dictionary_dict["PDFVersion"] = v_raw
                self.graph.add(
                    (
                        self.n_pdf_file_facet,
                        NS_UCO_OBSERVABLE.version,
                        rdflib.Literal(v_raw.toPython()),
                    )
                )
        elif exiftool_iri == "http://ns.exiftool.org/PDF/PDF/1.0/PageCount":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                self.pdf_dictionary_dict["PageCount"] = v_raw
                self.graph.add(
                    (
                        self.n_pdf_file_facet,
                        NS_DRAFTING.pdfPageCount,
                        rdflib.Literal(v_raw.toPython()),
                    )
                )
        elif exiftool_iri == "http://ns.exiftool.org/PDF/PDF/1.0/Producer":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                self.pdf_dictionary_dict["Producer"] = v_raw
                self.graph.add(
                    (
                        self.n_pdf_file_facet,
                        NS_DRAFTING.pdfProducer,
                        rdflib.Literal(v_raw.toPython()),
                    )
                )
        elif exiftool_iri == "http://ns.exiftool.org/PDF/PDF/1.0/Subject":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                self.pdf_dictionary_dict["Subject"] = v_raw
                self.graph.add(
                    (
                        self.n_pdf_file_facet,
                        NS_DRAFTING.pdfSubject,
                        rdflib.Literal(v_raw.toPython()),
                    )
                )
        elif exiftool_iri == "http://ns.exiftool.org/PDF/PDF/1.0/Title":
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if isinstance(v_raw, rdflib.Literal):
                self.pdf_dictionary_dict["Title"] = v_raw
                self.graph.add(
                    (
                        self.n_pdf_file_facet,
                        NS_DRAFTING.pdfTitle,
                        rdflib.Literal(v_raw.toPython()),
                    )
                )
        else:
            # Somewhat in the name of information preservation, somewhat as a progress marker on converting data: Attach all remaining unconverted properties directly to the ObservableObject.  Provide both values to assist with mapping decisions.
            (v_raw, v_printconv) = self.pop_n_exiftool_predicate(n_exiftool_predicate)
            if v_raw is not None:
                self.graph.add((self.n_observable_object, n_exiftool_predicate, v_raw))
            if v_printconv is not None:
                self.graph.add(
                    (self.n_observable_object, n_exiftool_predicate, v_printconv)
                )

    def map_raw_and_printconv_rdf(
        self,
        filepath_raw_xml: typing.Optional[str] = None,
        filepath_printconv_xml: typing.Optional[str] = None,
    ) -> None:
        """
        Loads the print-conv and raw graphs into a dictionary for processing by consuming known IRIs.

        This function has a side effect of mutating the internal variables:
        * self._kv_dict_raw
        * self._kv_dict_raw
        * self._exiftool_predicate_iris
        """

        # Output key: Graph predicate from file RDF-corrected IRI.
        # Output value: Object (whether Literal or URIRef).
        def _load_xml_file_into_dict(
            xml_file: str, kv_dict: typing.Dict[rdflib.URIRef, rdflib.term.Node]
        ) -> None:
            with contextlib.closing(rdflib.Graph()) as in_graph:
                in_graph.parse(xml_file, format="xml")
                for triple in in_graph.triples((None, None, None)):
                    # v_object might be a literal, might be an object reference.  "v" for "varying".  Because some properties are binary, do not decode v_object.
                    (
                        n_subject,
                        n_predicate,
                        v_object,
                    ) = triple
                    assert isinstance(n_predicate, rdflib.URIRef)
                    kv_dict[n_predicate] = v_object

        self._exiftool_predicate_iris: typing.Set[rdflib.URIRef] = set()
        if filepath_raw_xml is not None:
            _load_xml_file_into_dict(filepath_raw_xml, self._kv_dict_raw)
            self._exiftool_predicate_iris |= set(self._kv_dict_raw.keys())
        if filepath_printconv_xml is not None:
            _load_xml_file_into_dict(filepath_printconv_xml, self._kv_dict_printconv)
            self._exiftool_predicate_iris |= set(self._kv_dict_printconv.keys())

        # Start by mapping some IRIs that affect the base observable object.
        self.map_raw_and_printconv_iri(
            rdflib.URIRef("http://ns.exiftool.org/File/1.0/MIMEType")
        )

        # Finish special case MIME type processing left undone by map_raw_and_printconv_iri.
        if self.mime_type is not None:
            self.graph.add(
                (
                    self.n_content_data_facet,
                    NS_UCO_OBSERVABLE.mimeType,
                    rdflib.Literal(self.mime_type),
                )
            )
        # Define the raster picture facet depending on MIME type.
        mime_type_to_picture_type = {"image/jpeg": "jpg"}
        if self.mime_type in mime_type_to_picture_type:
            l_picture_type = rdflib.Literal(mime_type_to_picture_type[self.mime_type])
            self.graph.add(
                (
                    self.n_raster_picture_facet,
                    NS_UCO_OBSERVABLE.pictureType,
                    l_picture_type,
                )
            )

        # Create independent sorted copy of IRI set, because this iteration loop will mutate the set.
        sorted_exiftool_predicate_iris = sorted(self._exiftool_predicate_iris)
        for exiftool_predicate_iri in sorted_exiftool_predicate_iris:
            self.map_raw_and_printconv_iri(exiftool_predicate_iri)

        # Derive remaining objects.
        if self._exif_dictionary_dict is not None:
            _ = self.n_exif_dictionary_object
        if self._pdf_dictionary_dict is not None:
            _ = self.n_pdf_dictionary_object
        if self._n_location_object is not None:
            _ = self.n_relationship_object_location

    def pop_n_exiftool_predicate(
        self, n_exiftool_predicate: rdflib.URIRef
    ) -> typing.Tuple[
        typing.Optional[rdflib.term.Node], typing.Optional[rdflib.term.Node]
    ]:
        """
        Returns: (raw_object, printconv_object) from input graphs.

        This function has a side effect of mutating the internal variables:
        * self._kv_dict_raw
        * self._kv_dict_raw
        * self._exiftool_predicate_iris
        The exiftool_iri is removed from each of these dicts and set.
        """
        assert isinstance(n_exiftool_predicate, rdflib.URIRef)
        v_raw = None
        v_printconv = None
        if n_exiftool_predicate in self._exiftool_predicate_iris:
            self._exiftool_predicate_iris -= {n_exiftool_predicate}
        if n_exiftool_predicate in self._kv_dict_raw:
            v_raw = self._kv_dict_raw.pop(n_exiftool_predicate)
        if n_exiftool_predicate in self._kv_dict_printconv:
            v_printconv = self._kv_dict_printconv.pop(n_exiftool_predicate)
        return (v_raw, v_printconv)

    @property
    def exif_dictionary_dict(self) -> typing.Dict[str, rdflib.Literal]:
        """
        Initialized on first access.
        """
        if self._exif_dictionary_dict is None:
            self._exif_dictionary_dict = dict()
        return self._exif_dictionary_dict

    @property
    def pdf_dictionary_dict(self) -> typing.Dict[str, rdflib.Literal]:
        """
        Initialized on first access.
        Controlled dictionary keys reference terms from ISO 32000-1:2008 PDF Table 317 and ExifTool Tag Names.
        """
        if self._pdf_dictionary_dict is None:
            self._pdf_dictionary_dict = dict()
        return self._pdf_dictionary_dict

    @property
    def graph(self) -> rdflib.Graph:
        """
        No setter provided.
        """
        return self._graph

    @property
    def mime_type(self) -> typing.Optional[str]:
        return self._mime_type

    @mime_type.setter
    def mime_type(self, value: str) -> None:
        assert isinstance(value, str)
        self._mime_type = value
        if value == "application/pdf":
            self.graph.add(
                (self.n_observable_object, NS_RDF.type, NS_UCO_OBSERVABLE.PDFFile)
            )
        elif self.mime_type == "image/jpeg":
            self.graph.add(
                (self.n_observable_object, NS_RDF.type, NS_UCO_OBSERVABLE.RasterPicture)
            )

        else:
            _logger.warning("TODO - MIME type %r not yet implemented." % self.mime_type)

        # Access observable object to instantiate it with the oo_slug value.

    @property
    def n_camera_object(self) -> rdflib.URIRef:
        """
        Initialized on first access.
        """
        if self._n_camera_object is None:
            self._n_camera_object = self.ns_base["Device-" + local_uuid()]
            self.graph.add(
                (self._n_camera_object, NS_RDF.type, NS_UCO_OBSERVABLE.ObservableObject)
            )
        return self._n_camera_object

    @property
    def n_camera_object_device_facet(self) -> rdflib.URIRef:
        """
        Initialized on first access.
        """
        if self._n_camera_object_device_facet is None:
            if self.use_deterministic_uuids:
                self._n_camera_object_device_facet = (
                    case_utils.inherent_uuid.get_facet_uriref(
                        self.n_camera_object,
                        NS_UCO_OBSERVABLE.DeviceFacet,
                        namespace=self.ns_base,
                    )
                )
            else:
                self._n_camera_object_device_facet = self.ns_base[
                    "DeviceFacet-" + local_uuid()
                ]
            self.graph.add(
                (
                    self._n_camera_object_device_facet,
                    NS_RDF.type,
                    NS_UCO_OBSERVABLE.DeviceFacet,
                )
            )
            self.graph.add(
                (
                    self.n_camera_object,
                    NS_UCO_CORE.hasFacet,
                    self._n_camera_object_device_facet,
                )
            )
        return self._n_camera_object_device_facet

    @property
    def n_content_data_facet(self) -> rdflib.URIRef:
        """
        Initialized on first access.
        """
        if self._n_content_data_facet is None:
            if self.use_deterministic_uuids:
                self._n_content_data_facet = case_utils.inherent_uuid.get_facet_uriref(
                    self.n_observable_object,
                    NS_UCO_OBSERVABLE.ContentDataFacet,
                    namespace=self.ns_base,
                )
            else:
                self._n_content_data_facet = self.ns_base[
                    "ContentDataFacet-" + local_uuid()
                ]
            self.graph.add(
                (
                    self._n_content_data_facet,
                    NS_RDF.type,
                    NS_UCO_OBSERVABLE.ContentDataFacet,
                )
            )
            self.graph.add(
                (
                    self.n_observable_object,
                    NS_UCO_CORE.hasFacet,
                    self._n_content_data_facet,
                )
            )
        return self._n_content_data_facet

    @property
    def n_exif_dictionary_object(self) -> rdflib.URIRef:
        """
        Initialized on first access.
        """
        if self._n_exif_dictionary_object is None:
            self._n_exif_dictionary_object = controlled_dictionary_object_to_node(
                self.graph, self.ns_base, self.exif_dictionary_dict
            )
            self.graph.add(
                (
                    self.n_exif_facet,
                    NS_UCO_OBSERVABLE.exifData,
                    self._n_exif_dictionary_object,
                )
            )
        return self._n_exif_dictionary_object

    @property
    def n_exif_facet(self) -> rdflib.URIRef:
        """
        Initialized on first access.
        """
        if self._n_exif_facet is None:
            if self.use_deterministic_uuids:
                self._n_exif_facet = case_utils.inherent_uuid.get_facet_uriref(
                    self.n_observable_object,
                    NS_UCO_OBSERVABLE.EXIFFacet,
                    namespace=self.ns_base,
                )
            else:
                self._n_exif_facet = self.ns_base["EXIFFacet-" + local_uuid()]
            self.graph.add(
                (self._n_exif_facet, NS_RDF.type, NS_UCO_OBSERVABLE.EXIFFacet)
            )
            self.graph.add(
                (self.n_observable_object, NS_UCO_CORE.hasFacet, self._n_exif_facet)
            )
        return self._n_exif_facet

    @property
    def n_file_facet(self) -> rdflib.URIRef:
        """
        Initialized on first access.
        """
        if self._n_file_facet is None:
            if self.use_deterministic_uuids:
                self._n_file_facet = case_utils.inherent_uuid.get_facet_uriref(
                    self.n_observable_object,
                    NS_UCO_OBSERVABLE.FileFacet,
                    namespace=self.ns_base,
                )
            else:
                self._n_file_facet = self.ns_base["FileFacet-" + local_uuid()]
            self.graph.add(
                (self._n_file_facet, NS_RDF.type, NS_UCO_OBSERVABLE.FileFacet)
            )
            self.graph.add(
                (self.n_observable_object, NS_UCO_CORE.hasFacet, self._n_file_facet)
            )
        return self._n_file_facet

    @property
    def n_location_object(self) -> rdflib.URIRef:
        """
        Initialized on first access.
        """
        if self._n_location_object is None:
            self._n_location_object = self.ns_base["Location-" + local_uuid()]
            self.graph.add(
                (self._n_location_object, NS_RDF.type, NS_UCO_LOCATION.Location)
            )
        return self._n_location_object

    @property
    def n_location_object_latlong_facet(self) -> rdflib.URIRef:
        """
        Initialized on first access.
        """
        if self._n_location_object_latlong_facet is None:
            if self.use_deterministic_uuids:
                self._n_location_object_latlong_facet = (
                    case_utils.inherent_uuid.get_facet_uriref(
                        self.n_location_object,
                        NS_UCO_LOCATION.LatLongCoordinatesFacet,
                        namespace=self.ns_base,
                    )
                )
            else:
                self._n_location_object_latlong_facet = self.ns_base[
                    "LatLongCoordinatesFacet-" + local_uuid()
                ]
            self.graph.add(
                (
                    self._n_location_object_latlong_facet,
                    NS_RDF.type,
                    NS_UCO_LOCATION.LatLongCoordinatesFacet,
                )
            )
            self.graph.add(
                (
                    self.n_location_object,
                    NS_UCO_CORE.hasFacet,
                    self._n_location_object_latlong_facet,
                )
            )
        return self._n_location_object_latlong_facet

    @property
    def n_observable_object(self) -> rdflib.URIRef:
        """
        Initialized on first access.
        """
        if self._n_observable_object is None:
            assert isinstance(self.oo_slug, str)
            self._n_observable_object = self.ns_base[self.oo_slug + local_uuid()]
            # TODO Prepare list of more interesting types on adoption of the UCO release providing the ObservableObject subclass hierarchy.
            self.graph.add(
                (
                    self._n_observable_object,
                    NS_RDF.type,
                    NS_UCO_OBSERVABLE.ObservableObject,
                )
            )
        return self._n_observable_object

    @property
    def n_raster_picture_facet(self) -> rdflib.URIRef:
        """
        Initialized on first access.
        """
        if self._n_raster_picture_facet is None:
            if self.use_deterministic_uuids:
                self._n_raster_picture_facet = (
                    case_utils.inherent_uuid.get_facet_uriref(
                        self.n_observable_object,
                        NS_UCO_OBSERVABLE.RasterPictureFacet,
                        namespace=self.ns_base,
                    )
                )
            else:
                self._n_raster_picture_facet = self.ns_base[
                    "RasterPictureFacet-" + local_uuid()
                ]
            self.graph.add(
                (
                    self._n_raster_picture_facet,
                    NS_RDF.type,
                    NS_UCO_OBSERVABLE.RasterPictureFacet,
                )
            )
            self.graph.add(
                (
                    self.n_observable_object,
                    NS_UCO_CORE.hasFacet,
                    self._n_raster_picture_facet,
                )
            )
        return self._n_raster_picture_facet

    @property
    def n_relationship_object_location(self) -> rdflib.URIRef:
        """
        Initialized on first access.
        """
        if self._n_relationship_object_location is None:
            self._n_relationship_object_location = self.ns_base[
                "Relationship-" + local_uuid()
            ]
            self.graph.add(
                (
                    self._n_relationship_object_location,
                    NS_RDF.type,
                    NS_UCO_CORE.Relationship,
                )
            )
            self.graph.add(
                (
                    self._n_relationship_object_location,
                    NS_UCO_CORE.source,
                    self.n_location_object,
                )
            )
            self.graph.add(
                (
                    self._n_relationship_object_location,
                    NS_UCO_CORE.target,
                    self.n_observable_object,
                )
            )
            self.graph.add(
                (
                    self._n_relationship_object_location,
                    NS_UCO_CORE.isDirectional,
                    rdflib.Literal(True),
                )
            )
            self.graph.add(
                (
                    self._n_relationship_object_location,
                    NS_UCO_CORE.kindOfRelationship,
                    rdflib.Literal("Extracted_From"),
                )
            )
        return self._n_relationship_object_location

    @property
    def n_unix_file_permissions_facet(self) -> rdflib.URIRef:
        """
        Initialized on first access.
        """
        if self._n_unix_file_permissions_facet is None:
            if self.use_deterministic_uuids:
                self._n_unix_file_permissions_facet = (
                    case_utils.inherent_uuid.get_facet_uriref(
                        self.n_observable_object,
                        NS_UCO_OBSERVABLE.UNIXFilePermissionsFacet,
                        namespace=self.ns_base,
                    )
                )
            else:
                self._n_unix_file_permissions_facet = self.ns_base[
                    "UNIXFilePermissionsFacet-" + local_uuid()
                ]
            self.graph.add(
                (
                    self._n_unix_file_permissions_facet,
                    NS_RDF.type,
                    NS_UCO_OBSERVABLE.UNIXFilePermissionsFacet,
                )
            )
            self.graph.add(
                (
                    self.n_observable_object,
                    NS_UCO_CORE.hasFacet,
                    self._n_unix_file_permissions_facet,
                )
            )
        return self._n_unix_file_permissions_facet

    @property
    def ns_base(self) -> rdflib.Namespace:
        return self._ns_base

    @ns_base.setter
    def ns_base(self, value: rdflib.Namespace) -> None:
        assert isinstance(value, rdflib.Namespace)
        self._ns_base = value

    @property
    def oo_slug(self) -> typing.Optional[str]:
        return self._oo_slug

    @oo_slug.setter
    def oo_slug(self, value: str) -> None:
        assert isinstance(value, str)
        self._oo_slug = value

    @property
    def n_pdf_file_facet(self) -> rdflib.URIRef:
        """
        Initialized on first access.
        """
        if self._n_pdf_file_facet is None:
            if self.use_deterministic_uuids:
                self._n_pdf_file_facet = case_utils.inherent_uuid.get_facet_uriref(
                    self.n_observable_object,
                    NS_UCO_OBSERVABLE.PDFFileFacet,
                    namespace=self.ns_base,
                )
            else:
                self._n_pdf_file_facet = self.ns_base["PDFFileFacet-" + local_uuid()]
            self.graph.add(
                (self._n_pdf_file_facet, NS_RDF.type, NS_UCO_OBSERVABLE.PDFFileFacet)
            )
            self.graph.add(
                (self.n_observable_object, NS_UCO_CORE.hasFacet, self._n_pdf_file_facet)
            )
        return self._n_pdf_file_facet

    @property
    def n_pdf_dictionary_object(self) -> rdflib.URIRef:
        """
        Initialized on first access.
        """
        if self._n_pdf_dictionary_object is None:
            self._n_pdf_dictionary_object = controlled_dictionary_object_to_node(
                self.graph, self.ns_base, self.pdf_dictionary_dict
            )
            self.graph.add(
                (
                    self.n_pdf_file_facet,
                    NS_UCO_OBSERVABLE.documentInformationDictionary,
                    self._n_pdf_dictionary_object,
                )
            )
        return self._n_pdf_dictionary_object

    @property
    def use_deterministic_uuids(self) -> bool:
        """
        No setter provided.
        """
        return self._use_deterministic_uuids


def main() -> None:
    cdo_local_uuid.configure()

    args = argument_parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    NS_BASE = rdflib.Namespace(args.base_prefix)
    out_graph = rdflib.Graph()

    out_graph.namespace_manager.bind("drafting", NS_DRAFTING)
    out_graph.namespace_manager.bind("exiftool-Composite", NS_EXIFTOOL_COMPOSITE)
    out_graph.namespace_manager.bind("exiftool-et", NS_EXIFTOOL_ET)
    out_graph.namespace_manager.bind("exiftool-ExifTool", NS_EXIFTOOL_EXIFTOOL)
    out_graph.namespace_manager.bind("exiftool-System", NS_EXIFTOOL_SYSTEM)
    out_graph.namespace_manager.bind("exiftool-PDF-PDF", NS_EXIFTOOL_PDF_PDF)
    out_graph.namespace_manager.bind("exiftool-File", NS_EXIFTOOL_FILE)
    out_graph.namespace_manager.bind("exiftool-GPS", NS_EXIFTOOL_GPS)
    out_graph.namespace_manager.bind("exiftool-IFD0", NS_EXIFTOOL_IFD0)
    out_graph.namespace_manager.bind("exiftool-ExifIFD", NS_EXIFTOOL_EXIFIFD)
    out_graph.namespace_manager.bind("exiftool-Nikon", NS_EXIFTOOL_NIKON)
    out_graph.namespace_manager.bind("exiftool-PreviewIFD", NS_EXIFTOOL_PREVIEWIFD)
    out_graph.namespace_manager.bind("exiftool-InteropIFD", NS_EXIFTOOL_INTEROPIFD)
    out_graph.namespace_manager.bind("exiftool-IFD1", NS_EXIFTOOL_IFD1)
    out_graph.namespace_manager.bind("kb", NS_BASE)
    out_graph.namespace_manager.bind("uco-core", NS_UCO_CORE)
    out_graph.namespace_manager.bind("uco-identity", NS_UCO_IDENTITY)
    out_graph.namespace_manager.bind("uco-location", NS_UCO_LOCATION)
    out_graph.namespace_manager.bind("uco-observable", NS_UCO_OBSERVABLE)
    out_graph.namespace_manager.bind("uco-types", NS_UCO_TYPES)

    exiftool_rdf_mapper = ExifToolRDFMapper(
        out_graph, NS_BASE, use_deterministic_uuids=args.use_deterministic_uuids
    )
    exiftool_rdf_mapper.map_raw_and_printconv_rdf(args.raw_xml, args.print_conv_xml)

    # _logger.debug("args.output_format = %r." % args.output_format)
    output_format = args.output_format or rdflib.util.guess_format(args.out_graph)
    assert isinstance(output_format, str)

    out_graph.serialize(destination=args.out_graph, format=output_format)


if __name__ == "__main__":
    main()
