#!/usr/bin/env python3
"""Transforme les reponses brutes en table analysable.

Un modele ne respecte pas toujours la consigne de format. Les ecarts ne sont pas
des incidents techniques a nettoyer : ce sont des donnees. Un modele qui repond
juste mais hors format n'est pas equivalent a un modele qui repond juste et
proprement, et la proportion de sorties exploitables est un resultat en soi.

Regles appliquees :

- On tente d'abord le JSON strict, puis le JSON entoure de texte ou de balises
  de code, puis le dernier objet accolade de la reponse. Rien au-dela : pas
  d'extraction du verdict par expression reguliere dans de la prose, qui
  reviendrait a deviner ce que le modele n'a pas dit.
- Un verdict absent ou hors {0,1} donne statut = illisible, et la ligne est
  conservee. Elle compte dans le taux de conformite au format et, selon le
  mode d'analyse choisi, soit comme echec, soit comme donnee manquante. Les
  deux lectures sont fournies : les ecarter en silence surestimerait les
  modeles bavards.
- La localisation n'est evaluee que sur les items reellement ablates, et
  seulement quand le verdict vaut 0 : localiser un manque inexistant n'a pas
  de sens.

Sortie : resultats_parses.csv
"""
import csv, json, pathlib, re, sys

BRUTS = pathlib.Path("resultats_bruts.jsonl")
SORTIE = pathlib.Path("resultats_parses.csv")

try:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from localisation import Juge
    JUGE = Juge()
except Exception as _e:                     # manifeste absent : appariement exact
    JUGE = None

BLOC = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.S)
ACCOLADES = re.compile(r"\{.*\}", re.S)
CONFIANCES = {"high", "medium", "low"}


def extraire_json(txt):
    """Renvoie (objet, methode) ou (None, raison)."""
    if not txt or not txt.strip():
        return None, "reponse vide"
    t = txt.strip()
    try:
        return json.loads(t), "json_strict"
    except json.JSONDecodeError:
        pass
    m = BLOC.search(t)
    if m:
        try:
            return json.loads(m.group(1)), "bloc_code"
        except json.JSONDecodeError:
            pass
    m = ACCOLADES.search(t)
    if m:
        bloc = m.group(0)
        try:
            return json.loads(bloc), "accolades"
        except json.JSONDecodeError:
            # virgule finale, guillemets typographiques : defauts frequents
            repare = re.sub(r",(\s*[}\]])", r"\1", bloc)
            repare = repare.replace("“", '"').replace("”", '"')
            try:
                return json.loads(repare), "accolades_reparees"
            except json.JSONDecodeError:
                return None, "json_illisible"
    return None, "aucun objet json"


def normaliser(nom):
    """Compare des noms d'entites sans se laisser arreter par la forme."""
    if not nom:
        return ""
    n = nom.strip().lower()
    n = re.sub(r"^(attack|ont|owl|rdfs?):", "", n)
    n = re.sub(r"[^a-z0-9]+", "", n)
    return n


def localisation_correcte(predit, reel):
    """Le modele a-t-il nomme la bonne entite ?

    Tolerant sur la forme, strict sur l'entite : on exige que le nom reel
    apparaisse dans la reponse normalisee. Le modele peut donc ajouter une
    explication, mais pas se tromper d'entite.
    """
    p, r = normaliser(predit), normaliser(reel)
    if not p or not r:
        return False
    return r in p or p in r


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--fichier", default=str(BRUTS))
    ap.add_argument("--sortie", default=str(SORTIE))
    a = ap.parse_args()
    bruts, sortie = pathlib.Path(a.fichier), pathlib.Path(a.sortie)
    if not bruts.exists():
        sys.exit(f"{bruts} absent : lancer d'abord run_campaign.py")
    lignes = [json.loads(l) for l in open(bruts, encoding="utf-8")]

    # une empreinte ne doit etre comptee qu'une fois, meme si le fichier a ete
    # alimente par plusieurs executions successives
    vues, uniques = set(), []
    for l in lignes:
        if l["empreinte"] in vues:
            continue
        vues.add(l["empreinte"])
        uniques.append(l)

    out = []
    for l in uniques:
        base = {k: l.get(k) for k in (
            "empreinte", "prompt_version", "modele_demande", "modele_servi",
            "item_id", "cq_id", "stratum", "couverture", "condition", "lexique",
            "verite_terrain", "element_manquant_reel", "repetition", "horodatage",
            "hebergeur_demande", "fournisseur", "hebergeur_conforme",
            "item_reference", "item_sha256_12", "duree_s")}
        base["variante"] = l.get("variante", "base")
        u = l.get("usage") or {}
        base["jetons_entree"] = u.get("prompt_tokens", "")
        base["jetons_sortie"] = u.get("completion_tokens", "")
        base["cout_usd"] = u.get("cost", "")

        if l.get("erreur") and l.get("reponse_brute") is None:
            out.append({**base, "statut": "erreur_appel", "methode_extraction": "",
                        "verdict": "", "confiance": "", "element_manquant_predit": "",
                        "raisonnement": "", "localisation_correcte": "",
                        "detail": l["erreur"][:200]})
            continue

        obj, methode = extraire_json(l.get("reponse_brute"))
        if obj is None:
            out.append({**base, "statut": "illisible", "methode_extraction": methode,
                        "verdict": "", "confiance": "", "element_manquant_predit": "",
                        "raisonnement": "", "localisation_correcte": "",
                        "detail": (l.get("reponse_brute") or "")[:200]})
            continue

        v = obj.get("verdict")
        if isinstance(v, str) and v.strip() in ("0", "1"):
            v = int(v.strip())
        if v not in (0, 1):
            out.append({**base, "statut": "verdict_invalide",
                        "methode_extraction": methode, "verdict": "",
                        "confiance": str(obj.get("confidence", ""))[:20],
                        "element_manquant_predit": str(obj.get("missing_element", ""))[:200],
                        "raisonnement": str(obj.get("reasoning", ""))[:400],
                        "localisation_correcte": "", "detail": f"verdict={v!r}"})
            continue

        conf = str(obj.get("confidence", "")).strip().lower()
        pred = str(obj.get("missing_element", "") or "")
        loc = ""
        if l["couverture"] == "ablate" and v == 0:
            # regle par type d'ablation (localisation.py) ; repli sur
            # l'appariement exact si le manifeste ne connait pas l'item
            r = JUGE.juger(l["cq_id"], l["condition"], pred) if JUGE else None
            loc = int(r) if r is not None else int(localisation_correcte(pred, l["element_manquant_reel"]))

        out.append({**base, "statut": "ok", "methode_extraction": methode,
                    "verdict": v,
                    "confiance": conf if conf in CONFIANCES else "",
                    "element_manquant_predit": pred[:300],
                    "raisonnement": str(obj.get("reasoning", ""))[:600],
                    "localisation_correcte": loc, "detail": ""})

    with open(sortie, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader(); w.writerows(out)

    n = len(out)
    par_statut = {}
    for r in out:
        par_statut[r["statut"]] = par_statut.get(r["statut"], 0) + 1
    print(f"{n} reponses -> {sortie}")
    for s, c in sorted(par_statut.items(), key=lambda x: -x[1]):
        print(f"  {s:18} {c:5d}  {c/n:6.1%}")
    meth = {}
    for r in out:
        if r["statut"] == "ok":
            meth[r["methode_extraction"]] = meth.get(r["methode_extraction"], 0) + 1
    print("  extraction :", meth)
    sans_conf = sum(1 for r in out if r["statut"] == "ok" and not r["confiance"])
    if sans_conf:
        print(f"  confiance absente ou hors nomenclature : {sans_conf}")


if __name__ == "__main__":
    main()
