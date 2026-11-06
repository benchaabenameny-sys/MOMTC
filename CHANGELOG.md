# Changelog

All notable changes to MOMTC are documented here. Versions follow semantic versioning.

## [2.0.0] — 2026-11

Major revision, described in the journal article (under review).

### Added
- Module F, *Human Factors and Insider Threat* (`Human_Factor`, `Insider_Threat`, `Organizational_Role`,
  `Security_Awareness_Level`, `Human_Error_Type`, `Intent`), linked to attack vectors, targeted assets,
  countermeasures and techniques.
- Classes and properties in the other modules, for a total of 42 classes, 73 object properties and
  27 data properties, including the CAPEC, CPE, EPSS, NIST SP 800-53 and STIX sophistication alignments.
- OWL 2 axioms: six inverse pairs, four symmetric and three transitive properties, the property chain
  `exhibits_weakness ∘ is_child_of_weakness ⊑ transitively_exhibits`, two union domains and the
  disjointness of `Insider_Threat` and `Threat_Actor_Profiling`.
- Population with the Akira ransomware case study (joint advisory AA24-109A): 110 individuals covering
  all 42 classes.
- 39 competency questions with their SPARQL queries.
- `has_sophistication_rank` (functional data property) and the seven ranked values of the STIX
  threat-actor sophistication vocabulary; this addition (24 axioms, none removed) results from the
  LLM-assisted evaluation of competency question CQ1.

### Changed
- Ontology IRI: `http://w3id.org/momtc#` (stable from this version), with version IRI
  `http://w3id.org/momtc/2.0.0`.
- Naming of entities harmonised across modules.

## [1.0.0] — 2026-08-01

First public version, accompanying the SINCONF 2026 conference paper: five modules, 26 classes,
52 object properties, 21 data properties, 44 individuals, 444 axioms (301 logical).
