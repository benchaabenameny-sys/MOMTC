#!/usr/bin/env python3
"""Extrait, pour chaque CQ, le fragment TBox limite aux modules concernes.
C'est ce fragment qui sera envoye aux modeles de langage comme contexte,
et c'est aussi celui que l'annotateur humain verra lors de la session en aveugle.

Chaque fragment est un document OWL 2 autonome : toute entite citee par un
axiome du fragment y est declaree, meme si sa classe appartient a un autre
module. Sans cela le fragment n'est pas du OWL 2 valide et le stimulus est
mal forme.
"""
import re, csv, pathlib, hashlib

TBOX = open(str(pathlib.Path(__file__).resolve().parent / "momtc_tbox_corrige.ofn"), encoding="utf-8").read()

# --- classes par module ----------------------------------------------------
MOD = {
 "A": ["Threat_Actor_Profiling","Threat_Campaign","Sophistication_Level","Motivation",
       "Threat_Life_cycle_Status","Threat_Maturity","Threat_Category","Threat_Behavior",
       "Threat_Capability","Infrastructure"],
 "B": ["MITRE_ATT&CK:Offensive_Techniques","MITRE_ATT&CK:Sub-Technique","MITRE_ATT&CK:Tactics",
       "Attack_Vector","Attack_Vector_Type","CAPEC:Attack_Pattern","Platform"],
 "C": ["CVE_Vulnerabilities","CWE_Weakness","CVE_Products","CPE_Platform",
       "Risk_Assessment","Severity_Level","Indicators_Of_Compromise"],
 "D": ["Temporal_Execution","Threat_Impact","Impact_Type","Targeted_Asset",
       "Asset_Criticality_Level"],
 "E": ["D3FEND_Countermeasure","D3FEND_Sub_Countermeasure","D3FEND_Defensive_Tactics",
       "Detection_Mechanism","D3FEND_Digital_Artifact","Security_Control","Mitigation_Status"],
 "F": ["Human_Factor","Intent","Organizational_Role","Human_Error_Type",
       "Security_Awareness_Level","Insider_Threat"],
}

def full(c):
    """Nom local -> forme telle qu'elle apparait dans le fichier .ofn.

    L'ontologie d'origine n'est pas homogene : les entites MITRE ATT&CK sont
    ecrites en IRI complet, celles de CAPEC avec le prefixe attack:. On
    reproduit cette ecriture telle quelle plutot que de la normaliser, pour
    que les fragments restent des extraits litteraux de la TBox.
    """
    if c.startswith("MITRE_ATT&CK:"):
        return f"<https://attack.mitre.org/{c}>"
    return "attack:" + c

# Les fragments sont des extraits de TBox : aucune assertion d'individu.
ABOX_PREFIXES = ("Declaration(NamedIndividual(", "ClassAssertion(",
                 "ObjectPropertyAssertion(", "DataPropertyAssertion(",
                 "NegativeObjectPropertyAssertion(", "SameIndividual(",
                 "DifferentIndividuals(")

LINES = [l for l in TBOX.splitlines()
         if l.strip() and not l.strip().startswith("#")
         and not l.startswith(ABOX_PREFIXES)]

# --- index global des declarations -----------------------------------------
KIND = {}   # entite -> Class | ObjectProperty | DataProperty
for l in LINES:
    m = re.match(r"Declaration\((Class|ObjectProperty|DataProperty)\((.+?)\)\)", l)
    if m:
        KIND[m.group(2)] = m.group(1)

# Les noms locaux peuvent contenir ':' (attack:CAPEC:Attack_Pattern) et '&'
# (MITRE_ATT&CK:...). On les capture sans les tronquer au premier deux-points.
ENTITY_RE = re.compile(r"(attack:[A-Za-z0-9_&.:\-]+|<https://attack\.mitre\.org/[^>]+>)")

def entities(line):
    return set(ENTITY_RE.findall(line))

def props_in_scope(cls_forms):
    """Object/data properties dont domain OU range tombe dans le perimetre."""
    keep = set()
    for m in re.finditer(r"(Object|Data)Property(Domain|Range)\((attack:\S+) (.+)\)", TBOX):
        prop, expr = m.group(3), m.group(4)
        if any(c in expr for c in cls_forms):
            keep.add(prop)
    return keep

def build(modules):
    cls_forms = [full(c) for m in modules for c in MOD[m]]
    props = props_in_scope(cls_forms)
    scope = set(cls_forms) | props

    axioms = [l for l in LINES
              if not l.startswith(("Declaration(", "Prefix(", "Ontology(", ")"))
              and entities(l) & scope]

    # toute entite citee par un axiome retenu doit etre declaree
    cited = set()
    for l in axioms:
        cited |= entities(l)
    cited |= scope
    cited = {e for e in cited if e in KIND}

    decl_cls  = sorted(e for e in cited if KIND[e] == "Class")
    decl_obj  = sorted(e for e in cited if KIND[e] == "ObjectProperty")
    decl_data = sorted(e for e in cited if KIND[e] == "DataProperty")

    body = (["Prefix(attack:=<https://attack.mitre.org/>)",
             "Prefix(xsd:=<http://www.w3.org/2001/XMLSchema#>)",
             "",
             "Ontology(<http://w3id.org/momtc#>",
             ""]
            + [f"Declaration(Class({e}))" for e in decl_cls] + [""]
            + [f"Declaration(ObjectProperty({e}))" for e in decl_obj]
            + [f"Declaration(DataProperty({e}))" for e in decl_data] + [""]
            + axioms + ["", ")"])
    return "\n".join(body), len(decl_cls), len(decl_obj) + len(decl_data), len(axioms)

def undeclared(text):
    decl = set(re.findall(r"Declaration\((?:Class|ObjectProperty|DataProperty)\((.+?)\)\)", text))
    used = set(ENTITY_RE.findall(text))
    return sorted(used - decl)

if __name__ == "__main__":
    out = pathlib.Path("fragments/natural"); out.mkdir(parents=True, exist_ok=True)
    rows, defauts = [], 0
    for r in csv.DictReader(open(str(pathlib.Path(__file__).resolve().parent / "01_cqs.csv"), encoding="utf-8")):
        mods = [m.strip() for m in r["modules_involved"].split(";") if m.strip()]
        frag, nc, np_, na = build(mods)

        # 1. aucune entite non declaree
        u = undeclared(frag)
        # 2. tous les elements requis par la CQ sont presents
        req = [x for x in (r["required_classes"].split(";")
                           + r["required_properties"].split(";")
                           + r["required_data_properties"].split(";")) if x]
        manquants = [e for e in req if e not in frag]
        if u or manquants:
            defauts += 1
            print(f"  {r['cq_id']}: non declarees={u}  requis manquants={manquants}")

        (out / f"{r['cq_id']}.ofn").write_text(frag, encoding="utf-8")
        rows.append((r["cq_id"], r["stratum"], ";".join(mods), nc, np_, na,
                     len(frag), hashlib.sha256(frag.encode()).hexdigest()[:12]))

    with open("fragments_index.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cq_id","stratum","modules","classes","properties","axiomes",
                    "taille_car","sha256_12"])
        w.writerows(rows)

    print(f"{len(rows)} fragments ecrits, {defauts} en defaut")
    print(f"taille  min {min(r[6] for r in rows)}  max {max(r[6] for r in rows)}  "
          f"moy {sum(r[6] for r in rows)//len(rows)} caracteres")
