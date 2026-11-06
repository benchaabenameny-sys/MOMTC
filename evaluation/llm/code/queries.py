#!/usr/bin/env python3
"""Les 39 requetes SPARQL de MOMTC, testees contre l'ABox Akira."""

PREFIX = """PREFIX attack: <https://attack.mitre.org/>
PREFIX rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs:   <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:    <http://www.w3.org/2001/XMLSchema#>
"""

Q = {}

# ---------------- Module A -------------------------------------------------
Q["CQ1"] = """SELECT ?actor ?level WHERE {
  ?actor rdf:type attack:Threat_Actor_Profiling ;
         attack:has_sophistication_level ?level .
}"""

Q["CQ2"] = """SELECT ?campaign ?start ?end WHERE {
  attack:Akira attack:orchestrates ?campaign .
  OPTIONAL { ?campaign attack:has_temporal_execution ?w .
             ?w attack:has_start_time ?start ; attack:has_end_time ?end . }
}"""

Q["CQ3"] = """SELECT ?capability WHERE {
  attack:Akira attack:employs_capability ?capability .
}"""

Q["CQ4"] = """SELECT ?infra ?vector WHERE {
  attack:Akira attack:controls_infrastructure ?infra .
  OPTIONAL { ?infra attack:supports_attack_vector ?vector . }
}"""

Q["CQ5"] = """SELECT ?other WHERE {
  attack:Akira attack:is_behaviorally_similar_to ?other .
}"""

# ---------------- Module B -------------------------------------------------
Q["CQ6"] = """SELECT ?sub ?subid WHERE {
  ?sub attack:is_part_of_technique attack:T1566_Phishing .
  OPTIONAL { ?sub attack:has_sub_technique_id ?subid . }
}"""

Q["CQ7"] = """SELECT ?technique ?vector ?category WHERE {
  ?technique attack:utilizes_attack_vector ?vector .
  OPTIONAL { ?vector attack:has_vector_category ?category . }
}"""

Q["CQ8"] = """SELECT ?technique ?capecid WHERE {
  ?technique attack:realizes_attack_pattern ?pattern .
  OPTIONAL { ?pattern attack:has_capec_identifier ?capecid . }
}"""

Q["CQ9"] = """SELECT ?before WHERE {
  ?before attack:precedes_tactic attack:TA0040_Impact .
}"""

Q["CQ10"] = """SELECT ?technique ?platform WHERE {
  ?technique attack:applies_to_platform ?platform .
}"""

# ---------------- Module C -------------------------------------------------
Q["CQ11"] = """SELECT ?cwe ?cweid WHERE {
  attack:CVE_2020_3259 attack:transitively_exhibits ?cwe .
  OPTIONAL { ?cwe attack:has_cwe_identifier ?cweid . }
}"""

Q["CQ12"] = """SELECT ?cveid ?severity ?cvss ?epss ?date WHERE {
  ?cve attack:has_cve_identifier ?cveid ;
       attack:has_risk_assessment ?ra .
  OPTIONAL { ?ra attack:has_severity ?severity }
  OPTIONAL { ?ra attack:has_cvss_base_score ?cvss }
  OPTIONAL { ?ra attack:has_epss_score ?epss }
  OPTIONAL { ?ra attack:has_assessment_date ?date }
}"""

Q["CQ13"] = """SELECT ?source ?ioc ?pattern WHERE {
  ?source attack:generates_indicator ?ioc .
  OPTIONAL { ?ioc attack:has_indicator_pattern ?pattern . }
}"""

Q["CQ14"] = """SELECT ?product ?cpeid WHERE {
  attack:CVE_2023_20269 attack:affects ?product .
  OPTIONAL { ?product attack:is_identified_by ?cpe .
             ?cpe attack:has_cpe_identifier ?cpeid . }
}"""

Q["CQ15"] = """SELECT ?cveid WHERE {
  ?cve attack:has_cve_identifier ?cveid ;
       attack:has_risk_assessment ?ra .
  ?ra attack:is_known_exploited "true"^^xsd:boolean .
}"""

# ---------------- Module D -------------------------------------------------
Q["CQ16"] = """SELECT ?technique ?start ?end WHERE {
  attack:Akira_Execution_Window attack:executes_technique ?technique ;
                                attack:has_start_time ?start ;
                                attack:has_end_time   ?end .
}"""

Q["CQ17"] = """SELECT ?impact ?type WHERE {
  attack:Akira_Execution_Window attack:results_in ?impact .
  ?impact attack:has_impact_type ?type .
}"""

Q["CQ18"] = """SELECT ?other WHERE {
  attack:VPN_Gateway_Asset attack:shares_critical_dependency_with ?other .
}"""

Q["CQ19"] = """SELECT ?asset ?level ?weight WHERE {
  ?asset rdf:type attack:Targeted_Asset ;
         attack:has_asset_criticality ?level .
  OPTIONAL { ?level attack:has_criticality_weight ?weight . }
}"""

Q["CQ20"] = """SELECT ?technique ?trisk ?cveid ?cvss WHERE {
  ?technique attack:has_execution_risk_score ?trisk .
  OPTIONAL { ?technique attack:exploits_weakness ?cwe .
             ?cve attack:exhibits_weakness ?cwe ;
                  attack:has_cve_identifier ?cveid ;
                  attack:has_risk_assessment ?ra .
             ?ra attack:has_cvss_base_score ?cvss . }
}"""

# ---------------- Module E -------------------------------------------------
Q["CQ21"] = """SELECT ?cm WHERE {
  ?cm attack:mitigates attack:T1078_Valid_Accounts .
}"""

Q["CQ22"] = """SELECT ?cm ?mechanism ?ioc WHERE {
  ?cm attack:employs_detection_mechanism ?mechanism .
  OPTIONAL { ?mechanism attack:detects ?ioc . }
}"""

Q["CQ23"] = """SELECT ?cm ?status ?score WHERE {
  ?cm rdf:type attack:D3FEND_Countermeasure .
  OPTIONAL { ?cm attack:has_implementation_status ?status }
  OPTIONAL { ?cm attack:has_effectiveness_score   ?score }
}"""

Q["CQ24"] = """SELECT ?cm ?control WHERE {
  ?cm attack:is_formalized_by ?control .
}"""

Q["CQ25"] = """SELECT ?technique ?cm ?artifact WHERE {
  ?technique attack:tech_relates_to_artifact ?artifact .
  ?cm        attack:cm_relates_to_artifact   ?artifact .
}"""

# ---------------- Module F -------------------------------------------------
Q["CQ26"] = """SELECT ?hf ?intent WHERE {
  ?hf attack:has_intent ?intent .
}"""

Q["CQ27"] = """SELECT ?subject ?role WHERE {
  { ?subject attack:has_organizational_role ?role }
  UNION
  { ?subject attack:has_assigned_role ?role }
}"""

Q["CQ28"] = """SELECT ?hf ?error WHERE {
  ?hf attack:exhibits_error_type ?error .
}"""

Q["CQ29"] = """SELECT ?insider ?score ?technique WHERE {
  ?insider rdf:type attack:Insider_Threat .
  OPTIONAL { ?insider attack:has_insider_risk_score ?score }
  OPTIONAL { ?insider attack:is_realized_via ?technique }
}"""

Q["CQ30"] = """SELECT ?hf ?level WHERE {
  ?hf attack:has_awareness_level ?level .
}"""

# ---------------- Cross-module ---------------------------------------------
Q["CQ31"] = """SELECT DISTINCT ?technique ?cwe WHERE {
  attack:Akira attack:orchestrates ?campaign .
  ?campaign attack:campaign_employs ?technique .
  ?technique attack:exploits_weakness ?cwe .
}"""

Q["CQ32"] = """SELECT ?cm ?technique WHERE {
  attack:CVE_2023_20269 attack:is_remediated_by ?cm .
  OPTIONAL { ?cm attack:mitigates ?technique . }
}"""

Q["CQ33"] = """SELECT ?vector ?hf ?cm WHERE {
  ?vector attack:exploits_human_factor ?hf .
  OPTIONAL { ?cm attack:addresses_human_factor ?hf . }
}"""

Q["CQ34"] = """SELECT ?ioc ?actor WHERE {
  ?ioc attack:is_attributable_to ?actor .
}"""

Q["CQ35"] = """SELECT ?technique ?impact WHERE {
  ?execution attack:results_in ?impact ;
             attack:executes_technique ?technique .
}"""

Q["CQ36"] = """SELECT ?asset ?role ?hf WHERE {
  ?asset attack:has_assigned_role ?role .
  OPTIONAL { ?hf attack:has_organizational_role ?role . }
}"""

Q["CQ37"] = """SELECT DISTINCT ?ioc ?mechanism WHERE {
  attack:CVE_2020_3259 attack:generates_indicator ?ioc .
  ?mechanism attack:detects ?ioc .
}"""

Q["CQ38"] = """SELECT ?asset WHERE {
  attack:Akira attack:orchestrates ?campaign .
  ?campaign attack:causes_impact ?impact .
  ?impact attack:impacts_asset ?asset .
}"""

Q["CQ39"] = """SELECT ?cm ?technique WHERE {
  ?cm attack:defends_asset attack:VPN_Gateway_Asset .
  OPTIONAL { ?cm attack:mitigates ?technique . }
}"""

if __name__ == "__main__":
    from rdflib import Graph
    import sys
    g = Graph(); g.parse("momtc_akira.ttl", format="turtle")
    empty, total = [], 0
    for cq in sorted(Q, key=lambda x: int(x[2:])):
        rows = list(g.query(PREFIX + Q[cq]))
        total += 1
        flag = "" if rows else "   <<< VIDE"
        print(f"{cq:6s} {len(rows):4d} resultat(s){flag}")
        if not rows: empty.append(cq)
    print(f"\n{total - len(empty)}/{total} requetes retournent des resultats")
    if empty: print("Vides :", empty)
