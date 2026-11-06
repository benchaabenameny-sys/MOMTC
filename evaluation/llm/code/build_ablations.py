#!/usr/bin/env python3
"""Construit les 12 fragments ablates qui servent de negatifs controles.

Pourquoi : une ontologie correctement construite couvre ses propres CQ, donc le
gold standard naturel a une prevalence de 1.00 et aucune metrique d'accord n'est
calculable. Les negatifs doivent etre fabriques, de facon controlee et verifiable.
C'est l'equivalent ontologique du mutation testing.

Trois conditions, quatre items chacune :

  A1  suppression        une propriete requise par la CQ est retiree du fragment,
                         ainsi que tous les axiomes qui la mentionnent.
  A2  recablage          la propriete requise reste, mais son domaine ou son
                         codomaine est redirige vers une classe incompatible :
                         elle ne peut plus relier ce que la CQ demande.
  A3  quasi-correspondance  la propriete requise est remplacee par une AUTRE
                         propriete reellement presente dans MOMTC, proche
                         semantiquement (meme codomaine, domaine different, ou
                         l'inverse) mais incapable de repondre a la question.

Verite terrain : verdict = 0 pour les douze, par construction. Elle ne depend
d'aucun jugement, ni du mien ni de celui de l'annotateur.

Selection : allocation proportionnelle par strate avec methode des plus forts
restes, departages par un tirage de graine fixe (SEED). Entierement reproductible.

Aucune entite n'est inventee : toute propriete substituee existe deja dans la
TBox de MOMTC.
"""
import re, csv, json, random, pathlib, hashlib, sys


def graine_stable(*parties):
    """Entier deterministe derive d'une chaine.

    La fonction hash() de Python est randomisee a chaque execution
    (PYTHONHASHSEED) : l'utiliser pour deriver une graine rend la selection
    irreproductible d'un lancement a l'autre, meme a graine fixe. SHA-256 donne
    la meme valeur partout et toujours.
    """
    return int(hashlib.sha256("|".join(map(str, parties)).encode()).hexdigest(), 16)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from queries import Q as SPARQL

SEED = 42
N_ABL = 12
TBOX_PATH = str(pathlib.Path(__file__).resolve().parent / "momtc_tbox_corrige.ofn")
CQ_PATH = str(pathlib.Path(__file__).resolve().parent / "01_cqs.csv")
NAT = pathlib.Path("fragments/natural")
OUT = pathlib.Path("fragments/ablated")

TBOX = open(TBOX_PATH, encoding="utf-8").read()
ENTITY_RE = re.compile(r"(attack:[A-Za-z0-9_&.:\-]+|<https://attack\.mitre\.org/[^>]+>)")


# --------------------------------------------------------------------------
# index des domaines et codomaines, pour raisonner sur la proximite semantique
# --------------------------------------------------------------------------
def index_domains_ranges(text):
    """Domaines et codomaines par propriete.

    Le codomaine d'une data property est un type xsd, pas une classe : il faut
    le capturer aussi, sinon toutes les data properties paraissent avoir un
    codomaine vide et deviennent faussement interchangeables.
    """
    dom, rng = {}, {}
    for m in re.finditer(r"(?:Object|Data)PropertyDomain\((\S+) (.+)\)\n", text):
        dom.setdefault(m.group(1), set()).update(ENTITY_RE.findall(m.group(2)))
    for m in re.finditer(r"(?:Object|Data)PropertyRange\((\S+) (.+)\)\n", text):
        vals = ENTITY_RE.findall(m.group(2)) or re.findall(r"xsd:\w+", m.group(2))
        rng.setdefault(m.group(1), set()).update(vals)
    return dom, rng


DOM, RNG = index_domains_ranges(TBOX)

KIND = {}
for _m in re.finditer(r"Declaration\((ObjectProperty|DataProperty)\((\S+?)\)\)", TBOX):
    KIND[_m.group(2)] = _m.group(1)


def near_misses(prop):
    """Proprietes reelles, proches de `prop` mais incapables de la remplacer.

    Critere mecanique : meme codomaine et domaine different, ou meme domaine et
    codomaine different. Dans les deux cas la propriete ne relie pas les memes
    classes, donc elle ne repond pas a la question.

    La substitution reste du MEME type (object pour object, data pour data) :
    echanger une object property contre une data property serait une erreur
    grossiere, pas une quasi-correspondance, et rendrait la condition A3
    triviale alors qu'elle doit etre la plus difficile des trois.
    """
    d, r, k = DOM.get(prop, set()), RNG.get(prop, set()), KIND.get(prop)
    out = []
    for q in set(DOM) | set(RNG):
        if q == prop or KIND.get(q) != k:
            continue
        dq, rq = DOM.get(q, set()), RNG.get(q, set())
        meme_range = r and rq and r == rq and d != dq
        meme_dom = d and dq and d == dq and r != rq
        if meme_range or meme_dom:
            out.append(q)
    return sorted(out)


# --------------------------------------------------------------------------
# operations d'ablation
# --------------------------------------------------------------------------
def op_a1(frag, prop):
    """Retire la propriete et tout axiome qui la mentionne."""
    kept = [l for l in frag.splitlines() if prop not in ENTITY_RE.findall(l)]
    return "\n".join(kept)


def op_a2(frag, prop, remplacant):
    """Redirige le domaine de `prop` vers une classe incompatible."""
    out, touche = [], False
    for l in frag.splitlines():
        m = re.match(r"((?:Object|Data)PropertyDomain\(" + re.escape(prop) + r" )(.+)\)$", l)
        if m:
            out.append(f"{m.group(1)}{remplacant})")
            touche = True
        else:
            out.append(l)
    return "\n".join(out), touche


def op_a3(frag, prop, substitut):
    """Remplace `prop` par `substitut`, en declarant le substitut si besoin."""
    lignes = [l for l in frag.splitlines() if prop not in ENTITY_RE.findall(l)]
    txt = "\n".join(lignes)

    # axiomes du substitut, repris litteralement de la TBox
    ajouts = [l for l in TBOX.splitlines()
              if substitut in ENTITY_RE.findall(l)
              and l.startswith(("ObjectPropertyDomain(", "ObjectPropertyRange(",
                                "DataPropertyDomain(", "DataPropertyRange("))]
    kind = "ObjectProperty" if f"Declaration(ObjectProperty({substitut}))" in TBOX else "DataProperty"
    decl = f"Declaration({kind}({substitut}))"

    out = []
    for l in txt.splitlines():
        out.append(l)
        if l.startswith("Declaration(ObjectProperty(") and decl not in txt and kind == "ObjectProperty":
            pass
    txt = txt.replace("\n\n)", "\n)")  # normalise la fin

    corps = txt.rsplit("\n)", 1)
    nouveau = corps[0]
    if decl not in nouveau:
        nouveau = nouveau.replace("\nObjectPropertyDomain(", f"\n{decl}\nObjectPropertyDomain(", 1) \
            if "\nObjectPropertyDomain(" in nouveau else nouveau + "\n" + decl
    for a in ajouts:
        if a not in nouveau:
            nouveau += "\n" + a
    return nouveau + "\n\n)"


# --------------------------------------------------------------------------
# quelles proprietes peut-on casser sans laisser un chemin de reponse ouvert
# --------------------------------------------------------------------------
def porteuses(cq, props):
    """Proprietes dont la perte casse vraiment la question.

    Une propriete qui n'apparait que dans un OPTIONAL, ou dans une seule
    branche d'un UNION, laisse la requete repondre par ailleurs : la casser ne
    produit pas un negatif franc et la verite terrain 0 serait contestable.
    """
    q = SPARQL.get(cq, "")
    obligatoire = re.sub(r"OPTIONAL\s*\{[^{}]*\}", "", q, flags=re.S)
    return [p for p in props if p.split(":")[-1].rstrip(">") in obligatoire]


def union_dans_requete(cq):
    return "UNION" in SPARQL.get(cq, "")


# --------------------------------------------------------------------------
# selection stratifiee reproductible
# --------------------------------------------------------------------------
def selection(cqs, n, seed):
    strates = {}
    for r in cqs:
        # une requete a UNION offre toujours une branche de repli : exclue du
        # tirage, car aucune manipulation d'une seule propriete n'y donne un
        # negatif incontestable.
        if union_dans_requete(r["cq_id"]):
            continue
        strates.setdefault(r["stratum"], []).append(r["cq_id"])
    total = sum(len(v) for v in strates.values())
    quotas, restes = {}, {}
    for s, ids in strates.items():
        exact = len(ids) * n / total
        quotas[s] = int(exact)
        restes[s] = exact - int(exact)
    rng = random.Random(seed)
    manquant = n - sum(quotas.values())
    ordre = sorted(strates, key=lambda s: (-restes[s], rng.random()))
    for s in ordre[:manquant]:
        quotas[s] += 1
    ordre_strate = {}
    for s in sorted(strates):
        r2 = random.Random(graine_stable(seed, s))
        ordre_strate[s] = r2.sample(sorted(strates[s]), len(strates[s]))
    return ordre_strate, quotas


def fabriquer(cq, cond, cat, paires_utilisees):
    """Construit un item ablate, ou renvoie (None, raison) si c'est impossible."""
    r = cat[cq]
    frag = (NAT / f"{cq}.ofn").read_text(encoding="utf-8")
    props = [p for p in r["required_properties"].split(";") if p]
    if not props:
        return None, "aucune propriete requise"
    candidates = porteuses(cq, props)
    if not candidates:
        return None, "aucune propriete porteuse hors OPTIONAL"
    rl = random.Random(SEED + int(cq[2:]))
    cible = rl.choice(sorted(candidates))

    if cond == "A1":
        return (op_a1(frag, cible),
                {"operation": "suppression", "cible": cible}), None

    if cond == "A2":
        dom_orig = sorted(DOM.get(cible, []))
        remplacants = [c for c in sorted(set(ENTITY_RE.findall(frag)))
                       if c not in dom_orig and f"Declaration(Class({c}))" in frag]
        if not remplacants:
            return None, "aucune classe de remplacement"
        remp = rl.choice(remplacants)
        abl, touche = op_a2(frag, cible, remp)
        if not touche:
            return None, f"{cible} sans axiome de domaine"
        return (abl, {"operation": "recablage du domaine", "cible": cible,
                      "domaine_origine": dom_orig, "domaine_substitue": remp}), None

    # A3
    cands, retenue = [], cible
    for p in [cible] + [c for c in sorted(candidates) if c != cible]:
        c2 = [q for q in near_misses(p) if q not in props
              and (p, q) not in paires_utilisees]
        if c2:
            retenue, cands = p, c2
            break
    if not cands:
        return None, f"aucune quasi-correspondance inedite pour {cq}"
    sub = rl.choice(cands)
    paires_utilisees.add((retenue, sub))
    return (op_a3(frag, retenue, sub),
            {"operation": "quasi-correspondance", "cible": retenue, "substitut": sub,
             "domaine_cible": sorted(DOM.get(retenue, [])),
             "domaine_substitut": sorted(DOM.get(sub, [])),
             "codomaine_cible": sorted(RNG.get(retenue, [])),
             "codomaine_substitut": sorted(RNG.get(sub, []))}), None


# --------------------------------------------------------------------------
def main():
    cqs = list(csv.DictReader(open(CQ_PATH, encoding="utf-8")))
    cat = {r["cq_id"]: r for r in cqs}
    ordre_strate, quotas = selection(cqs, N_ABL, SEED)
    print("quotas par strate :", quotas)

    # un emplacement = (strate, condition). Les conditions sont reparties
    # 4/4/4 puis melangees a graine fixe.
    emplacements = []
    for s in sorted(quotas):
        emplacements += [s] * quotas[s]
    rng = random.Random(SEED)
    conditions = ["A1"] * 4 + ["A2"] * 4 + ["A3"] * 4
    rng.shuffle(conditions)

    OUT.mkdir(parents=True, exist_ok=True)
    manifeste, echecs = [], []
    paires_utilisees = set()          # pas deux fois la meme manipulation
    curseur = {s: 0 for s in quotas}  # ou en est le tirage dans chaque strate

    for strate, cond in zip(emplacements, conditions):
        resultat = None
        # on avance dans la strate jusqu'a trouver une CQ ou l'operation est
        # realisable ; les echecs sont traces, pas masques.
        while curseur[strate] < len(ordre_strate[strate]):
            cq = ordre_strate[strate][curseur[strate]]
            curseur[strate] += 1
            res, raison = fabriquer(cq, cond, cat, paires_utilisees)
            if res:
                resultat = (cq, res)
                break
            echecs.append((cq, cond, raison))
        if not resultat:
            echecs.append((strate, cond, "strate epuisee : emplacement non pourvu"))
            continue

        cq, (abl, detail) = resultat
        r = cat[cq]
        (OUT / f"{cq}_{cond}.ofn").write_text(abl, encoding="utf-8")
        manifeste.append({"item_id": f"{cq}_{cond}", "cq_id": cq, "stratum": r["stratum"],
                          "condition": cond, "verite_terrain": 0,
                          "element_manquant": detail.get("substitut") or detail.get("cible"),
                          "taille_car": len(abl),
                          "sha256_12": hashlib.sha256(abl.encode()).hexdigest()[:12],
                          **detail})

    json.dump(manifeste, open("ablation_manifest.json", "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    print(f"{len(manifeste)} fragments ablates ecrits dans {OUT}")
    if echecs:
        print("ECHECS :")
        for e in echecs:
            print("  ", e)


if __name__ == "__main__":
    main()
