#!/usr/bin/env python3
"""Controle de sensibilite au prompt (section 4.8).

Un verdict qui change parce qu'on a reformule la consigne, ou parce qu'on a
range les axiomes dans un autre ordre, n'est pas un verdict sur l'ontologie.
Les evaluateurs a base de modeles de langage sont documentes comme sensibles a
ces proprietes superficielles, l'ordre de presentation en particulier. Le taux
de bascule mesure cette fragilite et borne la confiance accordee a un resultat
obtenu avec un seul prompt.

Deux variantes, sur un sous-echantillon stratifie :

  paraphrase  la consigne de role est reecrite en d'autres termes, a contenu
              strictement identique. Aucune regle n'est ajoutee ni retiree :
              sinon on mesurerait l'effet d'une consigne differente, pas la
              sensibilite a la formulation.
  reordre     les axiomes du fragment sont permutes a graine fixe. La
              permutation reste a l'interieur de chaque bloc (declarations de
              classes, de proprietes, axiomes), de sorte que le document reste
              du OWL 2 valide et que seul l'ordre change.

Le verdict de reference est celui de la variante de base, sur le meme item.

Sortie : campaign_items_full.jsonl = items de base + items de sensibilite.
"""
import json, random, re, pathlib, hashlib


def graine_stable(*parties):
    """Graine deterministe : hash() de Python change a chaque execution."""
    return int(hashlib.sha256("|".join(map(str, parties)).encode()).hexdigest(), 16)

SEED = 515
N_SENS = 12            # items soumis aux deux variantes
BASE = pathlib.Path("campaign_items.jsonl")
SORTIE = pathlib.Path("campaign_items_full.jsonl")

# Consigne de role reecrite. Meme contenu, autre formulation.
ROLE_PARAPHRASE = (
    "Act as a knowledge engineer reviewing an OWL 2 ontology excerpt. Your job "
    "is to establish whether the excerpt supports a stated competency question. "
    "Return one JSON object only."
)


def reordonner(fragment, graine):
    """Permute les axiomes a l'interieur de chaque bloc, sans casser le document."""
    rng = random.Random(graine)
    lignes = fragment.splitlines()
    blocs, courant, type_courant = [], [], None

    def categorie(l):
        s = l.strip()
        if not s:
            return "vide"
        if s.startswith(("Prefix(", "Ontology(")) or s == ")":
            return "structure"
        if s.startswith("Declaration(Class("):
            return "decl_classe"
        if s.startswith(("Declaration(ObjectProperty(", "Declaration(DataProperty(")):
            return "decl_propriete"
        return "axiome"

    for l in lignes:
        c = categorie(l)
        if c != type_courant:
            if courant:
                blocs.append((type_courant, courant))
            courant, type_courant = [l], c
        else:
            courant.append(l)
    if courant:
        blocs.append((type_courant, courant))

    out = []
    for type_bloc, contenu in blocs:
        if type_bloc in ("decl_classe", "decl_propriete", "axiome") and len(contenu) > 1:
            melange = contenu[:]
            rng.shuffle(melange)
            out += melange
        else:
            out += contenu
    return "\n".join(out)


def main():
    items = [json.loads(l) for l in open(BASE, encoding="utf-8")]
    for it in items:
        it.setdefault("variante", "base")
        it.setdefault("role_paraphrase", False)

    # echantillon stratifie : couverture x lexique, pour que la sensibilite
    # soit mesuree aussi bien sur les positifs que sur les negatifs
    groupes = {}
    for it in items:
        groupes.setdefault((it["couverture"], it["lexique"]), []).append(it)
    rng = random.Random(SEED)
    par_groupe = max(1, N_SENS // len(groupes))
    choisis = []
    for cle in sorted(groupes):
        g = sorted(groupes[cle], key=lambda x: x["item_id"])
        choisis += rng.sample(g, min(par_groupe, len(g)))
    choisis = sorted(choisis, key=lambda x: x["item_id"])[:N_SENS]

    supplement = []
    for it in choisis:
        p = dict(it)
        p.update({"item_id": it["item_id"] + "_Vpara", "variante": "paraphrase",
                  "role_paraphrase": True, "item_reference": it["item_id"]})
        supplement.append(p)

        r = dict(it)
        r.update({"item_id": it["item_id"] + "_Vordre", "variante": "reordre",
                  "role_paraphrase": False, "item_reference": it["item_id"],
                  "fragment": reordonner(it["fragment"], graine_stable(SEED, it["item_id"]))})
        supplement.append(r)

    tous = items + supplement
    with open(SORTIE, "w", encoding="utf-8") as f:
        for it in tous:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    # controles : le reordonnancement ne doit rien ajouter ni retirer
    defauts = []
    for r in supplement:
        if r["variante"] != "reordre":
            continue
        base = next(i for i in items if i["item_id"] == r["item_reference"])
        if sorted(base["fragment"].split()) != sorted(r["fragment"].split()):
            defauts.append(r["item_id"])
        if base["fragment"] == r["fragment"]:
            defauts.append(r["item_id"] + " (inchange)")

    print(f"{len(items)} items de base + {len(supplement)} de sensibilite "
          f"= {len(tous)} -> {SORTIE}")
    print(f"  sous-echantillon : {len(choisis)} items, deux variantes chacun")
    print("  controle du reordonnancement :", defauts or "aucun defaut")


if __name__ == "__main__":
    main()
