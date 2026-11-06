# STIX 2.1 export

Export of the Akira case-study population of MOMTC v2.0.0 to a STIX 2.1 bundle (Appendix D of the article).

- `momtc_akira_stix21.json`: STIX 2.1 bundle (39 domain objects and 36 relationship objects)
- `export_stix.py`: export script; it reads `../serialisations/MOMTC.rdf`
- `export_report.json`: summary of the export
- `validate.py`: validation script
- `validation_report.json`: validation results

Only STIX 2.1 core objects, properties, vocabularies and relationship types are used. Identifiers are derived deterministically from the IRI of each individual, so the export is reproducible byte for byte. The bundle was validated with the OASIS validator (stix2-validator 3.3.1) in default and strict modes, with no error and no warning, and parsed with the OASIS stix2 library (3.0.2) with custom content disallowed.

Usage:

    pip install rdflib stix2 stix2-validator
    python export_stix.py
    python validate.py
