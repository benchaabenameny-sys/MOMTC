#!/usr/bin/env python3
"""Table de renommage lexical pour le controle de contamination (section 4.7).

Chaque mot porteur de sens des noms d'entites de MOMTC est remplace par un
quasi-synonyme. Les noms obtenus doivent rester AUSSI TRANSPARENTS que les
originaux, tout en ne coincidant jamais avec le vocabulaire publie de MOMTC.

Historique, a reporter dans le papier
-------------------------------------
Version 1 (abandonnee apres le pilote du 29 octobre 2026). Elle visait seulement
a changer la surface des noms. Le pilote a montre qu'elle degradait le sens :
les items naturels etaient acceptes a 100 % sous le vocabulaire d'origine et a
20 % sous le vocabulaire renomme, et les raisonnements des modeles designaient
precisement les noms fautifs :
  - MITRE_ATT&CK:Offensive_Techniques -> Registry_Reg_Cat_Aggressive_Methods :
    les fragments de sigle, traduits mot a mot, produisaient un bruit opaque ;
    un modele ecrivait que le fragment « n'a aucune classe Technique ».
  - mitigates -> contains : « contains » a un sens meronymique fort en
    ontologie et ne se lit pas comme une attenuation.
  - impacts_asset -> affectsResource_resource, belongs_to -> pertainsTo_to,
    Threat_Life_cycle_Status -> Adversary_Span_Loop_State : noms agrammaticaux.
Un controle de contamination dont le renommage degrade le sens mesure l'opacite
du vocabulaire, pas la memorisation : la baisse aurait ete attribuee a tort a
la contamination. D'ou cette version 2.

Version 2 : principes
  1. Transparence d'abord. Un quasi-synonyme courant, jamais un mot rare ni un
     terme qui a un autre sens technique en ontologie.
  2. Les fragments de sigles sans sens propre (MITRE, ATT, CK, CAPEC) sont
     SUPPRIMES plutot que traduits : le mot de domaine qui les suit porte deja
     le sens. Les sigles qui designent un objet (CVE, CWE, CPE, NVD, CVSS,
     EPSS, D3FEND) recoivent un nom commun qui dit ce qu'ils designent.
  3. Les mots grammaticaux et quelques verbes generiques (is, has, of, shares,
     similar...) restent tels quels : ils ne portent pas d'indice de
     memorisation et les remplacer ne ferait que nuire a la lecture. Le nom
     complet change toujours, puisque les mots de domaine qui l'entourent
     changent.
  4. Controles automatiques : aucun mot sans synonyme, aucune collision, aucun
     nom identique a l'original, aucun nom vide.
"""

import pathlib
# chaine vide = fragment de sigle supprime
SYNONYMES = {
    # sigles sans sens propre : supprimes
    "mitre": "", "att": "", "ck": "", "capec": "",
    # sigles qui designent un objet : nom commun explicite
    "cve": "Exposure", "cwe": "Flaw", "cpe": "Product", "nvd": "Catalog",
    "cvss": "Severity", "epss": "Exploit_Likelihood", "d3fend": "Defense",

    # acteurs, campagnes, capacites
    "threat": "Adversary", "actor": "Agent", "profiling": "Profile",
    "campaign": "Operation", "capability": "Capacity", "infrastructure": "Facility",
    "sophistication": "Expertise", "motivation": "Driver", "maturity": "Evolution",
    "category": "Grouping", "behavior": "Conduct", "behaviorally": "operationally",
    "lifecycle": "Trajectory", "life": "Activity", "cycle": "Phase",

    # techniques et vecteurs
    "attack": "Offense", "offensive": "Hostile", "defensive": "Protective",
    "technique": "Method", "techniques": "Methods", "tech": "method",
    "tactic": "Objective", "tactics": "Objectives", "sub": "Specific",
    "vector": "Channel", "pattern": "Template", "platform": "Environment",
    "part": "Segment",

    # vulnerabilites
    "vulnerabilities": "Defects", "weakness": "Shortcoming", "products": "Systems",
    "risk": "Hazard", "assessment": "Appraisal", "severity": "Seriousness",
    "score": "Rating", "base": "Core", "child": "Descendant",
    "exploited": "abused", "exploits": "abuses", "known": "confirmed",
    "entry": "Record", "identifier": "Code", "published": "released",
    "indicator": "Signal", "indicators": "Signals", "compromise": "Breach",
    "confidence": "Certainty",

    # execution, impact, actifs
    "temporal": "Chronological", "execution": "Run", "executes": "runs",
    "impact": "Consequence", "impacts": "harms", "type": "Kind",
    "asset": "Resource", "targeted": "Threatened", "targets": "threatens",
    "criticality": "Essentiality", "critical": "essential",
    "dependency": "Reliance", "weight": "Coefficient", "level": "Grade",
    # ajoute pour la revision de CQ1 (has_sophistication_rank) ; absent du fichier evalue
    "rank": "Tier",

    # defense
    "countermeasure": "Safeguard", "cm": "safeguard",
    "mitigates": "counters", "mitigated": "countered", "mitigation": "Countering",
    "detection": "Discovery", "detects": "discovers", "mechanism": "Procedure",
    "artifact": "Trace", "digital": "Electronic", "security": "Protection",
    "control": "Measure", "status": "State", "implementation": "Deployment",
    "implemented": "deployed", "effectiveness": "Potency",
    "defends": "guards", "remediated": "repaired", "formalized": "codified",
    "recommended": "advised",

    # facteur humain
    "human": "Personnel", "factor": "Trait", "insider": "Internal",
    "role": "Function", "organizational": "Institutional", "intent": "Purpose",
    "awareness": "Vigilance", "error": "Lapse", "addresses": "tackles",
    "assigned": "allotted",

    # verbes relationnels
    "generates": "yields", "orchestrates": "directs", "employs": "wields",
    "controls": "commands", "supports": "enables", "utilizes": "uses",
    "affects": "impairs", "realizes": "enacts", "realized": "enacted",
    "realization": "Enactment", "precedes": "predates", "applies": "pertains",
    "applied": "fitted", "belongs": "attaches", "transitively": "indirectly",
    "attributable": "ascribable", "attribution": "Ascription",
    "identified": "designated", "relates": "links", "provides": "supplies",
    "observed": "witnessed", "originates": "stems", "causes": "induces",
    "results": "culminates", "result": "Outcome", "leverages": "harnesses",
    "exhibits": "displays", "via": "through",

    # temps
    "date": "Day", "time": "Instant", "start": "Opening", "end": "Closing",
    "first": "Earliest", "last": "Latest", "access": "Entry",
}

# Noms complets fixes a la main, la ou la traduction mot a mot donne un nom
# vague ou trompeur. Chacun est justifie.
SURCHARGES = {
    # « capec » supprime laisse « has_code » : on ne saurait plus de quoi
    "has_capec_identifier": "has_template_code",
    # un vecteur CVSS est une chaine descriptive, pas un canal d'attaque
    "has_cvss_vector": "has_severity_descriptor",
    # casse irreguliere de l'original (Life_cycle) : on normalise
    "Threat_Life_cycle_Status": "Adversary_Activity_Phase_State",
}

# conserves tels quels : mots grammaticaux et verbes generiques sans valeur
# d'indice de memorisation
INVARIANTS = {"is", "has", "of", "by", "to", "with", "from", "in", "for", "id",
              "shares", "similar"}


def verifier(noms):
    """Construit la table et renvoie (table, sans_synonyme, inchanges, collisions)."""
    import re
    manquants, inchanges = set(), []
    table = {}
    for n in noms:
        if n in SURCHARGES:
            table[n] = SURCHARGES[n]
            continue
        morceaux = [w for w in re.split(r"[_:&\-]+", n) if w]
        out = []
        for w in morceaux:
            k = w.lower()
            if k in INVARIANTS:
                out.append(w)
            elif k in SYNONYMES:
                s = SYNONYMES[k]
                if not s:
                    continue                      # fragment de sigle supprime
                # casse d'origine : Classe ou propriete. Pour un synonyme en
                # plusieurs mots, toute la chaine suit la casse du mot remplace.
                out.append(s if w[0].isupper() else s.lower())
            else:
                manquants.add(k)
                out.append(w)
        nouveau = "_".join(out)
        if not nouveau or nouveau == n:
            inchanges.append(n)
        table[n] = nouveau
    valeurs = list(table.values())
    collisions = sorted({v for v in valeurs if valeurs.count(v) > 1})
    return table, sorted(manquants), inchanges, collisions


if __name__ == "__main__":
    import re
    t = open(str(pathlib.Path(__file__).resolve().parent / "momtc_tbox_corrige.ofn"), encoding="utf-8").read()
    noms = set(re.findall(
        r"Declaration\((?:Class|ObjectProperty|DataProperty)\((?:attack:|<https://attack\.mitre\.org/)([^)>]+)>?\)\)", t))
    table, manquants, inchanges, collisions = verifier(noms)
    print(f"{len(noms)} entites")
    print("mots sans synonyme :", manquants or "aucun")
    print("noms inchanges     :", inchanges or "aucun")
    print("collisions         :", collisions or "aucune")
    print()
    for n in sorted(noms, key=str.lower):
        print(f"   {n:48} -> {table[n]}")
