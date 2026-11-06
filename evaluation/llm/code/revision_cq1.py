#!/usr/bin/env python3
"""Revision de CQ1 declenchee par l'evaluation (Table 8), incluse dans MOMTC v2.0.0.

Desaccord E1 : « Advanced or higher » suppose un ordre entre niveaux de
sophistication, que la TBox evaluee n'exprime pas. Revision appliquee par
l'auteur dans Protege (MOMTC.owl, v2.0.0) :
  - propriete fonctionnelle has_sophistication_rank (Sophistication_Level ->
    xsd:integer), avec rdfs:comment ;
  - sept individus de Sophistication_Level suivant l'ordre du vocabulaire STIX
    threat-actor-sophistication-ov (none 1 ... strategic 7).

Ce script
  1. verifie que MOMTC.owl = ontologie evaluee + ces seuls axiomes ;
  2. construit la TBox revisee et le fragment CQ1 revise (meme procedure que pour
     les 39 fragments : module A, TBox seule) ;
  3. ajoute deux items de reverification (original et renomme_q) au fichier
     d'items, variante « revision_v11 » (etiquette interne attribuee pendant
     la campagne, conservee telle quelle dans le journal brut), sans toucher
     aux 177 items evalues.
"""
import hashlib, json, pathlib, re, sys

ICI = pathlib.Path(__file__).resolve().parent
V10 = ICI / "momtc_avec_akira.ofn"
V11 = pathlib.Path(str(pathlib.Path(__file__).resolve().parent.parents[2] / "MOMTC.owl"))
TBOX_V10 = pathlib.Path(str(pathlib.Path(__file__).resolve().parent / "momtc_tbox_corrige.ofn"))
TBOX_V11 = pathlib.Path(str(pathlib.Path(__file__).resolve().parent / "momtc_tbox_revised.ofn"))
ITEMS = ICI / "campaign_items_full.jsonl"
VARIANTE = "revision_v11"


def axiomes(path):
    out = set()
    for l in path.read_text(encoding="utf-8").splitlines():
        l = l.strip()
        if not l or l.startswith("#"):
            continue
        out.add(l.replace('"^^xsd:string)', '")'))   # forme equivalente en OWL 2
    return out


def main():
    # 1. difference exacte entre la version evaluee et la version revisee
    ajouts = axiomes(V11) - axiomes(V10)
    retraits = axiomes(V10) - axiomes(V11)
    ajouts.discard("<http://w3id.org/momtc/1.1.0>")    # IRI de version
    attendu = re.compile(r"has_sophistication_rank|Sophistication_Level attack:"
                         r"|NamedIndividual\(attack:(None|Minimal|Intermediate|Expert|Innovator|Strategic)\)")
    hors = [a for a in ajouts if not attendu.search(a)]
    print(f"axiomes ajoutes : {len(ajouts)}   retires : {len(retraits)}   hors revision : {len(hors)}")
    if retraits or hors:
        sys.exit(f"ARRET : difference inattendue\n retires={sorted(retraits)}\n hors={hors}")
    rangs = dict(re.findall(r'has_sophistication_rank attack:(\w+) "(\d+)"', "\n".join(ajouts)))
    attendus = {"None": "1", "Minimal": "2", "Intermediate": "3", "Advanced": "4",
                "Expert": "5", "Innovator": "6", "Strategic": "7"}
    if rangs != attendus:
        sys.exit(f"ARRET : rangs {rangs} != echelle STIX {attendus}")
    print("rangs conformes a l'echelle STIX :", rangs)

    # 2. TBox revisee = TBox evaluee + axiomes TBox de la revision
    abox = ("Declaration(NamedIndividual(", "ClassAssertion(", "DataPropertyAssertion(")
    tbox_ajouts = sorted(a for a in ajouts if not a.startswith(abox))
    t = TBOX_V10.read_text(encoding="utf-8").rstrip()
    assert t.endswith(")")
    TBOX_V11.write_text(t[:-1] + "\n# --- revision CQ1 ---\n"
                        + "\n".join(tbox_ajouts) + "\n)\n", encoding="utf-8")
    print(f"TBox revisee : {len(tbox_ajouts)} axiomes ajoutes -> {TBOX_V11}")

    src = (ICI / "build_fragments.py").read_text(encoding="utf-8")
    src = src.replace(str(TBOX_V10), str(TBOX_V11)).split('if __name__ == "__main__":')[0]
    ns = {}
    exec(compile(src, "build_fragments_v11", "exec"), ns)
    frag, nc, np_, na = ns["build"](["A"])
    requis = ["attack:Threat_Actor_Profiling", "attack:Sophistication_Level",
              "attack:has_sophistication_level", "attack:has_sophistication_rank"]
    manque = [r for r in requis if r not in frag]
    nd = ns["undeclared"](frag)
    if manque or nd:
        sys.exit(f"ARRET : fragment CQ1 revise incomplet {manque} / non declares {nd}")
    print(f"fragment CQ1 revise : {nc} classes, {np_} proprietes, {na} axiomes, OK")

    # 3. items de reverification
    from campaign_items import noms_locaux, table_renommage, renommer
    from questions_renommees import renommer_question
    items = [json.loads(l) for l in open(ITEMS, encoding="utf-8")]
    items = [i for i in items if i.get("variante") != VARIANTE]
    ref = {i["item_id"]: i for i in items}
    q_orig = ref["CQ1_naturel_orig"]["question"]
    q_ren = ref["CQ1_naturel_renomQ"]["question"]

    table = table_renommage(noms_locaux(frag))
    frag_r = renommer(frag, table)
    # le texte libre du commentaire suit la meme regle mot a mot que la question
    def com(m):
        txt, _ = renommer_question(m.group(1))
        return f'rdfs:comment ont:{m.group(0).split("ont:")[1].split(" ")[0]} "{txt}"'
    frag_r = re.sub(r'rdfs:comment ont:\S+ "([^"]*)"', com, frag_r)

    commun = {"cq_id": "CQ1", "stratum": "A", "couverture": "naturel",
              "condition": "naturel", "verite_terrain": 1, "element_manquant": "",
              "variante": VARIANTE, "role_paraphrase": False, "version_ontologie": "1.1"}
    nouveaux = [
        {**commun, "item_id": "CQ1_naturel_orig_v11", "lexique": "original",
         "question": q_orig, "fragment": frag, "item_reference": "CQ1_naturel_orig",
         "sha256_12": hashlib.sha256(frag.encode()).hexdigest()[:12]},
        {**commun, "item_id": "CQ1_naturel_renomQ_v11", "lexique": "renomme_q",
         "question": q_ren, "question_originale": q_orig, "fragment": frag_r,
         "table_renommage": table, "item_reference": "CQ1_naturel_renomQ",
         "sha256_12": hashlib.sha256(frag_r.encode()).hexdigest()[:12]},
    ]
    fuite = [w for w in ("sophistication", "Threat_Actor", "attack:", "mitre")
             if w.lower() in frag_r.lower()]
    if fuite:
        sys.exit(f"ARRET : vocabulaire d'origine dans le fragment renomme : {fuite}")
    with open(ITEMS, "w", encoding="utf-8") as f:
        for i in items + nouveaux:
            f.write(json.dumps(i, ensure_ascii=False) + "\n")
    print(f"{len(items)} items conserves + {len(nouveaux)} items de reverification -> {ITEMS.name}")
    print("sha256", ITEMS.name, hashlib.sha256(ITEMS.read_bytes()).hexdigest()[:16])
    pathlib.Path(ICI / "fragments" / "revision_v11").mkdir(parents=True, exist_ok=True)
    (ICI / "fragments" / "revision_v11" / "CQ1_v11.ofn").write_text(frag, encoding="utf-8")
    (ICI / "fragments" / "revision_v11" / "CQ1_v11_renomme.ofn").write_text(frag_r, encoding="utf-8")


if __name__ == "__main__":
    main()
