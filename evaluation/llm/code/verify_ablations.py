#!/usr/bin/env python3
"""Verifie que chaque fragment ablate constitue reellement un negatif.

Une ablation qui ne casse pas la question est pire qu'une ablation absente :
elle introduit une fausse verite terrain, et toutes les metriques calculees
ensuite sont fausses sans que rien ne le signale. Ce script est donc le garde-fou
du dispositif, et il doit passer a zero defaut avant toute campagne.

Controles :
  1. le fragment ablate est toujours du OWL 2 valide
  2. A1 : la cible a disparu ; tous les autres elements requis sont intacts
  3. A2 : la cible est presente mais son domaine ne contient plus la classe
          d'origine ; le domaine substitue est declare dans le fragment
  4. A3 : la cible a disparu, le substitut est present et declare, et son
          domaine ou son codomaine differe de celui de la cible
  5. le fragment ablate differe du fragment naturel
  6. RISQUE : la cible n'apparait-elle que dans un OPTIONAL ou une branche
     UNION de la requete SPARQL ? Si oui, la question reste peut-etre
     repondable par un autre chemin et la verite terrain 0 est contestable.
"""
import re, csv, json, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from queries import Q

ENTITY_RE = re.compile(r"(attack:[A-Za-z0-9_&.:\-]+|<https://attack\.mitre\.org/[^>]+>)")
NAT = pathlib.Path("fragments/natural")
ABL = pathlib.Path("fragments/ablated")
CAT = {r["cq_id"]: r for r in csv.DictReader(open(str(pathlib.Path(__file__).resolve().parent / "01_cqs.csv"), encoding="utf-8"))}


def declare(frag, e):
    return any(f"Declaration({k}({e}))" in frag for k in ("Class", "ObjectProperty", "DataProperty"))


def domaines(frag, prop):
    out = set()
    for m in re.finditer(r"(?:Object|Data)PropertyDomain\(" + re.escape(prop) + r" (.+)\)", frag):
        out |= set(ENTITY_RE.findall(m.group(1)))
    return out


def chemin_alternatif(cq, cible):
    """La cible est-elle confinee a un OPTIONAL ou a une branche UNION ?"""
    q = Q.get(cq, "")
    nom = cible.split(":")[-1].rstrip(">")
    if nom not in q:
        return "cible absente de la requete SPARQL"
    obligatoire = re.sub(r"OPTIONAL\s*\{[^{}]*\}", "", q, flags=re.S)
    if nom not in obligatoire:
        return "cible uniquement dans un OPTIONAL"
    if "UNION" in q:
        return "requete avec UNION : verifier qu'aucune branche ne repond seule"
    return None


def main():
    man = json.load(open("ablation_manifest.json", encoding="utf-8"))
    try:
        from funowl.converters.functional_converter import to_python
        parse = True
    except ImportError:
        parse = False
        print("funowl absent : controle de validite OWL ignore\n")

    defauts, risques = [], []
    for x in man:
        cq, cond, item = x["cq_id"], x["condition"], x["item_id"]
        cible = x["cible"]
        nat = (NAT / f"{cq}.ofn").read_text(encoding="utf-8")
        abl = (ABL / f"{item}.ofn").read_text(encoding="utf-8")
        r = CAT[cq]
        requis = [e for e in (r["required_classes"].split(";")
                              + r["required_properties"].split(";")
                              + r["required_data_properties"].split(";")) if e]
        pb = []

        if abl == nat:
            pb.append("identique au fragment naturel")

        if parse:
            tmp = pathlib.Path("/tmp/_abl_check.ofn"); tmp.write_text(abl, encoding="utf-8")
            try:
                to_python(str(tmp))
            except Exception as e:
                pb.append(f"OWL invalide : {type(e).__name__}")

        present = cible in ENTITY_RE.findall(abl)

        if cond == "A1":
            if present:
                pb.append(f"{cible} toujours presente")
            for e in requis:
                if e != cible and e not in abl:
                    pb.append(f"element requis collateral perdu : {e}")

        elif cond == "A2":
            if not present:
                pb.append(f"{cible} absente : ce n'est plus un recablage")
            d = domaines(abl, cible)
            for orig in x["domaine_origine"]:
                if orig in d:
                    pb.append(f"domaine d'origine {orig} toujours present")
            if x["domaine_substitue"] not in d:
                pb.append("domaine substitue absent")
            if not declare(abl, x["domaine_substitue"]):
                pb.append(f"{x['domaine_substitue']} non declaree dans le fragment")

        else:  # A3
            sub = x["substitut"]
            if present:
                pb.append(f"{cible} toujours presente")
            if sub not in ENTITY_RE.findall(abl):
                pb.append(f"substitut {sub} absent")
            if not declare(abl, sub):
                pb.append(f"substitut {sub} non declare")
            if (x["domaine_cible"] == x["domaine_substitut"]
                    and x["codomaine_cible"] == x["codomaine_substitut"]):
                pb.append("substitut de meme domaine ET meme codomaine : il repond peut-etre")

        risque = chemin_alternatif(cq, cible)
        if risque:
            risques.append((item, cible, risque))
        if pb:
            defauts.append((item, pb))

    print(f"{len(man)} items verifies\n")
    if defauts:
        print("DEFAUTS :")
        for item, pb in defauts:
            print(f"  {item}")
            for p in pb:
                print(f"     - {p}")
    else:
        print("Aucun defaut : les 12 ablations sont des negatifs valides.")

    if risques:
        print("\nA EXAMINER (verite terrain potentiellement contestable) :")
        for item, cible, r in risques:
            print(f"  {item:12} {cible:42} {r}")
    else:
        print("\nAucun chemin alternatif detecte.")

    return 1 if defauts else 0


if __name__ == "__main__":
    sys.exit(main())
