#!/usr/bin/env python3
"""Construit le jeu d'items soumis aux modeles de langage.

Deux dimensions croisees.

Couverture
  naturel   les 39 fragments intacts, verite terrain 1
  ablate    les 12 fragments manipules, verite terrain 0
  -> 51 items. Les modeles, contrairement a l'annotateur humain, peuvent voir
     une CQ sous ses deux formes sans que cela biaise quoi que ce soit : ils
     n'ont pas de memoire entre deux appels.

Lexique  (controle de contamination)
  original  les noms d'entites de MOMTC
  renomme   tout nom local est remplace par un identifiant neutre, la structure
            logique restant identique

Pourquoi le renommage : MOMTC est publie sur GitHub. Un modele dont la fenetre
d'entrainement couvre cette publication pourrait restituer de memoire plutot que
raisonner. Si les performances s'effondrent sur la version renommee, c'est de la
memorisation ; si elles tiennent, c'est du raisonnement structurel. Sans ce
controle, un relecteur est fonde a demander comment la contamination a ete
ecartee.

Sortie : campaign_items.jsonl, un objet par ligne.
"""
import re, csv, json, pathlib, hashlib

from lexique_renommage import verifier
NAT = pathlib.Path("fragments/natural")
ABL = pathlib.Path("fragments/ablated")
CQ_PATH = str(pathlib.Path(__file__).resolve().parent / "01_cqs.csv")
OUT = pathlib.Path("campaign_items.jsonl")

LOCAL_RE = re.compile(r"attack:([A-Za-z0-9_&.:\-]+)|<https://attack\.mitre\.org/([^>]+)>")


def noms_locaux(frag):
    out = set()
    for m in LOCAL_RE.finditer(frag):
        out.add(m.group(1) or m.group(2))
    return out


def table_renommage(noms):
    """Nom local -> quasi-synonyme, via la table lexicale partagee.

    Le renommage est deterministe : pas de tirage aleatoire, donc identique a
    chaque regeneration et verifiable par un relecteur.
    """
    table, manquants, inchanges, collisions = verifier(noms)
    if manquants or inchanges or collisions:
        raise SystemExit(f"table lexicale incomplete : sans synonyme={manquants} "
                         f"inchanges={inchanges} collisions={collisions}")
    # ordre des cles fixe : un ensemble Python n'a pas d'ordre stable d'une
    # execution a l'autre, et la table est ecrite telle quelle dans le JSON
    return dict(sorted(table.items()))


def renommer(frag, table):
    def sub(m):
        nom = m.group(1) or m.group(2)
        return "ont:" + table.get(nom, nom)
    out = LOCAL_RE.sub(sub, frag)
    # la declaration de prefixe n'est pas capturee par LOCAL_RE (le ':' y est
    # suivi d'un '='), il faut la remplacer a part, sinon le fragment renomme
    # continue de pointer vers le namespace de MOMTC et le controle fuit.
    out = out.replace("Prefix(attack:=<https://attack.mitre.org/>)",
                      "Prefix(ont:=<http://example.org/ontology#>)")
    out = out.replace("Ontology(<http://w3id.org/momtc#>",
                      "Ontology(<http://example.org/ontology#>")
    # Les annotations rdfs:comment citent parfois un nom d'entite en clair,
    # sans prefixe : LOCAL_RE ne le voit pas et le vocabulaire d'origine
    # ressortirait dans le texte des commentaires. On traite ces occurrences
    # nues, du nom le plus long au plus court pour eviter les recouvrements.
    for nom in sorted(table, key=lambda n: (-len(n), n)):
        out = re.sub(r"(?<![A-Za-z0-9_:])" + re.escape(nom) + r"(?![A-Za-z0-9_])",
                     table[nom], out)
    return out


def renommer_texte(txt, table):
    """Applique le renommage aux mentions d'entites dans une chaine libre."""
    for nom in sorted(table, key=lambda n: (-len(n), n)):
        txt = txt.replace(nom, table[nom])
    return txt


def main():
    cat = {r["cq_id"]: r for r in csv.DictReader(open(CQ_PATH, encoding="utf-8"))}
    man = json.load(open("ablation_manifest.json", encoding="utf-8"))

    base = []
    for cq, r in cat.items():
        base.append({"cq_id": cq, "stratum": r["stratum"], "couverture": "naturel",
                     "condition": "naturel", "verite_terrain": 1, "element_manquant": "",
                     "chemin": NAT / f"{cq}.ofn"})
    for x in man:
        base.append({"cq_id": x["cq_id"], "stratum": x["stratum"], "couverture": "ablate",
                     "condition": x["condition"], "verite_terrain": 0,
                     "element_manquant": x.get("substitut") or x["cible"],
                     "chemin": ABL / f"{x['item_id']}.ofn"})

    items = []
    for b in base:
        frag = b["chemin"].read_text(encoding="utf-8")
        question = cat[b["cq_id"]]["text"]
        cle_base = f"{b['cq_id']}_{b['condition']}"

        items.append({**{k: v for k, v in b.items() if k != "chemin"},
                      "item_id": f"{cle_base}_orig", "lexique": "original",
                      "question": question, "fragment": frag,
                      "sha256_12": hashlib.sha256(frag.encode()).hexdigest()[:12]})

        table = table_renommage(noms_locaux(frag))
        frag_r = renommer(frag, table)
        em = b["element_manquant"]
        em_r = table.get(em.replace("attack:", ""), "") if em else ""
        items.append({**{k: v for k, v in b.items() if k not in ("chemin", "element_manquant")},
                      "item_id": f"{cle_base}_renom", "lexique": "renomme",
                      "element_manquant": ("ont:" + em_r) if em_r else "",
                      "question": question, "fragment": frag_r,
                      "table_renommage": table,
                      "sha256_12": hashlib.sha256(frag_r.encode()).hexdigest()[:12]})

    with open(OUT, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    n1 = sum(1 for i in items if i["verite_terrain"] == 1)
    print(f"{len(items)} items -> {OUT}")
    print(f"  positifs {n1}  negatifs {len(items)-n1}  prevalence {n1/len(items):.3f}")
    for lex in ("original", "renomme"):
        s = [i for i in items if i["lexique"] == lex]
        print(f"  {lex:9} {len(s):3d} items, "
              f"{sum(1 for i in s if i['verite_terrain']==0)} negatifs")
    return items


if __name__ == "__main__":
    main()
