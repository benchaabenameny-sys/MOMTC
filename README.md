# MOMTC — Modular Ontology for Multidimensional Cyber Threat Classification

MOMTC is an OWL 2 DL ontology that represents cyber threats along six interconnected dimensions:
adversaries, attack techniques, vulnerabilities and weaknesses, attack execution and impact,
defensive countermeasures, and human factors. It reuses the identifiers of established standards
(MITRE ATT&CK, CAPEC, CVE, CWE, CPE, CVSS, EPSS, MITRE D3FEND, NIST SP 800-53, STIX 2.1) and links
them through explicit, reasoner-supported relations.

## Versions

| Version | Description | Publication |
|---|---|---|
| **v2.0.0** (this version) | Six modules, 42 classes, populated with the Akira ransomware case study; evaluated with SPARQL competency questions and an LLM-assisted protocol; aligned with STIX 2.1 | Journal article (under review) |
| [v1.0.0](https://github.com/benchaabenameny-sys/MOMTC/releases/tag/v1.0.0) | Five modules, 26 classes | SINCONF 2026 (conference paper) |

MOMTC follows semantic versioning. From v2.0.0 onwards, the ontology IRI is stable
(`http://w3id.org/momtc#`) and each release has its own version IRI (`http://w3id.org/momtc/2.0.0`).
The changes between versions are listed in [CHANGELOG.md](CHANGELOG.md).

## Ontology at a glance (v2.0.0)

| Element | Count |
|---|---|
| Modules | 6 (A Threat Intelligence and Adversary Profiling; B Attack Techniques and Vectors; C Vulnerabilities, Weaknesses and IoCs; D Attack Execution, Asset Targeting and Impact; E Defensive Strategies and Countermeasures; F Human Factors and Insider Threat) |
| Classes / object properties / data properties | 42 / 73 / 27 |
| Named individuals (Akira case study) | 120 |
| Axioms (logical) | 804 (540) |
| Competency questions | 39 (5 per module, 9 cross-module) |

The ontology is consistent under HermiT and contains no unsatisfiable class.

## Repository structure

```
MOMTC.owl                    MOMTC v2.0.0 (OWL functional syntax)
serialisations/              the same ontology in RDF/XML (MOMTC.rdf) and Turtle (MOMTC.ttl)
competency-questions/        the 39 competency questions, one SPARQL query per question, and the results
case-study/                  the Akira population: individuals with their sources, object and data assertions
evaluation/                  the exact file evaluated, and the data and code of the LLM-assisted evaluation
stix/                        export of the Akira case study to STIX 2.1, with the validation report
CHANGELOG.md, CITATION.cff, LICENSE
```

## Using the ontology

1. Open `MOMTC.owl` in [Protégé](https://protege.stanford.edu/) 5.6 or later.
2. Start the HermiT reasoner (*Reasoner → HermiT*, then *Start reasoner*).
3. Run the competency questions of `competency-questions/sparql/` with the Snap SPARQL plugin,
   in synchronising mode, so that queries are evaluated over the inferred model. Five questions
   (CQ9, CQ11, CQ13, CQ18, CQ23) depend on inference and return incomplete answers without a
   description-logic reasoner.

## Reproducing the evaluation

* **Competency questions.** `competency-questions/sparql_results.csv` gives, for each question, the
  expected and obtained number of rows and the schema- and instance-level verdicts (39/39).
* **LLM-assisted evaluation.** `evaluation/` contains the dataset (179 items), the prompts, the
  campaign log of all model calls, the analysis outputs and the code. See
  [evaluation/README.md](evaluation/README.md).
* **STIX 2.1 export.** `stix/export_stix.py` exports the case study to `stix/momtc_akira_stix21.json`;
  `stix/validate.py` validates it with the OASIS validator (default and strict modes: no error,
  no warning).

## Citation

If you use MOMTC, please cite the conference paper (v1.0.0) and, once published, the journal
article (v2.0.0). See [CITATION.cff](CITATION.cff).

> Ben Chaaben, A., Jouini, M., & Ben Arfa Rabai, L. (2026). A Modular Ontology for Multidimensional
> Cyber Threat Classification. In *Proceedings of the 18th International Conference on Security of
> Information and Networks (SINCONF 2026)*.

## License

MIT License — see [LICENSE](LICENSE).
