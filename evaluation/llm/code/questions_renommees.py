#!/usr/bin/env python3
"""Condition « renomme_q » : fragment renomme ET question renommee (section 4.7).

Pourquoi
--------
Dans la campagne principale, le renommage ne portait que sur le fragment ;
le texte de la CQ gardait le vocabulaire publie (« CAPEC attack pattern »,
« threat actor »...). L'analyse a montre que, sur les 39 CQ naturelles
renommees, des mots de la question presents dans le fragment d'origine
disparaissaient du fragment renomme, et que la quasi-totalite des rejets
d'items sains citaient precisement l'un de ces mots. La baisse observee
melangeait donc deux effets : perte d'indices memorises ET rupture du pont
lexical entre la question et le schema. Cette condition supprime le second
effet : la meme table de mots (lexique_renommage.SYNONYMES) est appliquee a la
question, mot par mot, comme elle l'a ete aux noms d'entites.

Regle, entierement mecanique
  - chaque mot de la question dont la forme minuscule (ou sa forme singulier /
    pluriel) figure dans SYNONYMES est remplace par son synonyme, accorde en
    nombre et dans la casse du mot d'origine ;
  - les fragments de sigle sans sens propre (MITRE, ATT, CK, CAPEC) sont
    supprimes, exactement comme dans les noms d'entites ;
  - tous les autres mots restent tels quels. Aucune reformulation a la main.

Sorties
  - campaign_items_full.jsonl : les 126 items existants, inchanges, suivis de
    51 items « renomme_q » (variante base). Les reponses deja en cache restent
    valides : leur empreinte ne change pas.
  - questions_renommees.csv : question d'origine et question renommee, pour
    l'annexe.
"""
import csv, hashlib, json, pathlib, re, sys

from lexique_renommage import SYNONYMES

ICI = pathlib.Path(__file__).resolve().parent
ITEMS = ICI / "campaign_items_full.jsonl"


# Mots de la prose generique que la table ne doit pas toucher dans une phrase :
# « time » n'a de synonyme (« Instant ») que comme modificateur dans un nom
# d'entite (first_observed_time...) ; « over instant » serait agrammatical.
INVARIANTS_QUESTION = {"time"}
IRREGULIERS_PARTICIPE = {"run": "run"}


def troisieme(base):
    if base.endswith(("ch", "sh", "s", "x")):
        return base + "es"
    if base.endswith("y") and base[-2:-1] not in "aeiou":
        return base[:-1] + "ies"
    return base + "s"


def base_de_troisieme(v):
    if v.endswith("ies"):
        return v[:-3] + "y"
    if v.endswith(("ches", "shes", "sses", "xes")):
        return v[:-2]
    return v[:-1] if v.endswith("s") else v


def base_de_participe(v):
    if v.endswith("ied"):
        return v[:-3] + "y"
    if v.endswith("ed"):
        b = v[:-2]
        # abused -> abuse, designated -> designate ; enacted -> enact
        return b + "e" if b.endswith(("us", "at", "iz", "ag", "uc", "ur")) else b
    return v


def participe(base):
    if base in IRREGULIERS_PARTICIPE:
        return IRREGULIERS_PARTICIPE[base]
    if base.endswith("e"):
        return base + "d"
    if base.endswith("y") and base[-2:-1] not in "aeiou":
        return base[:-1] + "ied"
    return base + "ed"


def gerondif(base):
    if base == "run":
        return "running"
    return (base[:-1] if base.endswith("e") and not base.endswith("ee") else base) + "ing"


def pluriel(nom):
    return troisieme(nom)


def singulier(nom):
    return base_de_troisieme(nom)


def verbe(base_mot):
    """Base verbale du synonyme d'une base verbale de la question, ou None.
    La table contient la 3e personne (controls), le participe (formalized) ou
    les deux ; on cherche l'une ou l'autre."""
    for cand in (troisieme(base_mot), base_mot + "s"):
        if cand in SYNONYMES and SYNONYMES[cand]:
            return base_de_troisieme(SYNONYMES[cand].lower())
    for cand in (participe(base_mot), base_mot + "ed", base_mot + "d"):
        if cand in SYNONYMES and SYNONYMES[cand]:
            return base_de_participe(SYNONYMES[cand].lower())
    return None


def chercher(mot, apres_auxiliaire):
    """Synonyme d'un mot de la question, accorde a sa forme."""
    k = mot.lower()
    if k in INVARIANTS_QUESTION:
        return None
    # sens verbal prioritaire apres « do/does » (Which infrastructure does a
    # given threat actor control) : controls -> commands, et non control -> Measure
    if apres_auxiliaire:
        v = verbe(k)
        if v:
            return v
    if k in SYNONYMES:
        return SYNONYMES[k]
    # noms au pluriel ou verbes a la 3e personne : forme de la table au singulier
    b = singulier(k)
    if b != k and b in SYNONYMES and SYNONYMES[b]:
        return pluriel(SYNONYMES[b])
    # noms au singulier dont la table ne connait que le pluriel
    if pluriel(k) in SYNONYMES and SYNONYMES[pluriel(k)]:
        return singulier(SYNONYMES[pluriel(k)])
    # verbes : 3e personne, participe, gerondif, base
    if k.endswith("s") and verbe(base_de_troisieme(k)):
        return troisieme(verbe(base_de_troisieme(k)))
    if k.endswith("ed"):
        for b in (k[:-1], k[:-2], k[:-3] + "y" if k.endswith("ied") else None):
            if b and verbe(b):
                return participe(verbe(b))
    if k.endswith("ing"):
        for b in (k[:-3], k[:-3] + "e"):
            if verbe(b):
                return gerondif(verbe(b))
    v = verbe(k)
    if v:
        return v
    return None


def casse(syn, mot):
    syn = syn.replace("_", " ")
    if mot.isupper() and len(mot) > 1:
        return syn                        # sigle -> nom commun en casse du synonyme
    if mot[0].isupper():
        return syn[0].upper() + syn[1:].lower() if syn else syn
    return syn.lower()


def renommer_question(q):
    # ATT&CK est un seul jeton de sigle : on le traite d'un bloc
    morceaux = re.split(r"([A-Za-z0-9]+(?:&[A-Za-z0-9]+)?)", q)
    out, subs, changes = [], [], set()
    vus = []
    for m in morceaux:
        if not m or not re.match(r"[A-Za-z0-9]", m):
            out.append(m)
            if m and re.search(r"[,?;.]", m):
                vus = []
            continue
        aux = any(w.lower() in ("do", "does") for w in vus[-5:])
        rempl = []
        for p in m.split("&"):
            syn = chercher(p, aux)
            rempl.append(p if syn is None else casse(syn, p))
        nouveau = "".join(x for x in rempl if x)
        if nouveau != m:
            subs.append(f"{m}->{nouveau or '(supprime)'}")
            changes.add(len(out))
        out.append(nouveau)
        vus.append(m)
    # accord de l'article devant un mot remplace (a expertise -> an expertise)
    for idx in sorted(changes):
        j = idx - 1
        while j >= 0 and not out[j].strip():
            j -= 1
        if j >= 0 and out[j].lower() in ("a", "an") and out[idx]:
            voy = out[idx][0].lower() in "aeiou"
            art = ("an" if voy else "a")
            out[j] = art if out[j].islower() else art.capitalize()
    texte = "".join(out)
    texte = re.sub(r"\s{2,}", " ", texte).replace(" ?", "?").replace(" ,", ",").strip()
    return texte, subs


def main():
    items = [json.loads(l) for l in open(ITEMS, encoding="utf-8")]
    deja = [i for i in items if i["lexique"] != "renomme_q"]
    base = [i for i in deja if i["lexique"] == "renomme" and i["variante"] == "base"]
    nouveaux, lignes = [], []
    for i in base:
        q2, subs = renommer_question(i["question"])
        n = dict(i)
        n["item_id"] = i["item_id"].replace("_renom", "_renomQ")
        n["lexique"] = "renomme_q"
        n["question"] = q2
        n["question_originale"] = i["question"]
        n["item_reference"] = n["item_id"]
        nouveaux.append(n)
        lignes.append({"item_id": n["item_id"], "cq_id": i["cq_id"],
                       "question_originale": i["question"], "question_renommee": q2,
                       "substitutions": "; ".join(subs)})
    # controles
    ids = [n["item_id"] for n in deja + nouveaux]
    assert len(ids) == len(set(ids)), "identifiants en double"
    restes = []
    for n in nouveaux:
        orig = next(i for i in deja if i["item_id"] == n["item_id"].replace("_renomQ", "_orig"))
        mots = lambda s: {w.lower() for w in re.findall(r"[A-Za-z]{3,}", s)}
        perdus = (mots(n["question"]) & mots(re.sub(r"[_:&]", " ", orig["fragment"]))) \
            - mots(re.sub(r"[_:&]", " ", n["fragment"]))
        if perdus:
            restes.append((n["item_id"], sorted(perdus)))
    with open(ITEMS, "w", encoding="utf-8") as f:
        for i in deja + nouveaux:
            f.write(json.dumps(i, ensure_ascii=False) + "\n")
    with open(ICI / "questions_renommees.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0]))
        w.writeheader()
        w.writerows(lignes)
    print(f"{len(deja)} items conserves, {len(nouveaux)} items renomme_q ajoutes "
          f"-> {len(deja) + len(nouveaux)}")
    print(f"questions ou un mot reste sans equivalent dans le fragment renomme : {len(restes)}")
    for r in restes:
        print("   ", r)
    h = hashlib.sha256(ITEMS.read_bytes()).hexdigest()[:16]
    print(f"sha256 {ITEMS.name} : {h}")


if __name__ == "__main__":
    main()
