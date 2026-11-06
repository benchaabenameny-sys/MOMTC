#!/usr/bin/env python3
"""Gabarits de prompt de la campagne.

Version figee : PROMPT_VERSION entre dans la cle de cache et dans chaque ligne
de resultat. Toute retouche du texte change la version, donc rien ne se melange
entre deux formulations et un relecteur sait exactement quel prompt a produit
quel chiffre.

Choix de conception, et leurs raisons :

- La tache donnee au modele est mot pour mot celle donnee a l'annotateur
  humain. Une comparaison homme-machine n'a de sens que si la consigne est la
  meme ; reformuler pour "aider" le modele fausserait l'ecart mesure.
- Le raisonnement est demande AVANT le verdict. Un verdict pose d'abord est
  ensuite justifie a posteriori, ce qui degrade la qualite et rend l'audit
  trompeur.
- missing_element est exige des que le verdict vaut 0 : detecter et localiser
  sont deux competences distinctes et on les mesure separement.
- Sortie en JSON strict, sans texte autour, pour que l'analyse syntaxique ne
  devienne pas elle-meme une source d'erreur attribuee au modele.
- Aucun exemple resolu n'est fourni. En montrer un revelerait la proportion
  d'items truques et deplacerait la mesure vers l'apprentissage en contexte.
"""

PROMPT_VERSION = "v1.0"

SYSTEME = (
    "You are an expert ontology engineer. You assess whether an OWL 2 ontology "
    "fragment contains the classes, properties and axioms required to answer a "
    "given competency question. You answer only with a single JSON object."
)

GABARIT = """Below is an ontology fragment in OWL 2 functional syntax, followed by a competency question.

Decide whether the fragment, as given, can answer the question.

Answer 1 only if every entity the question requires is present AND the properties actually connect the required classes. Check each property's domain and range, not only its name: a property whose domain or range does not match what the question needs does NOT satisfy the question, even if its name sounds right.

Answer 0 if anything required is absent, or present but wired to the wrong classes.

Judge only from the fragment shown. Do not rely on knowledge of any published ontology.

--- FRAGMENT ---
{fragment}
--- END FRAGMENT ---

COMPETENCY QUESTION: {question}

Reply with exactly this JSON object and nothing else:

{{"reasoning": "<two or three sentences naming the entities you looked for and what you found>",
 "verdict": <0 or 1>,
 "missing_element": "<if verdict is 0, the exact name of the entity that is absent or wrongly wired, and why; empty string if verdict is 1>",
 "confidence": "<high, medium or low>"}}"""


def construire(item):
    """Messages au format conversationnel pour un item de campagne.

    Les items de la condition de sensibilite (section 4.8) portent
    role_paraphrase = True : la consigne de role est alors reformulee, a
    contenu identique, pour mesurer le taux de bascule du verdict.
    """
    from prompt_variants import ROLE_PARAPHRASE
    systeme = ROLE_PARAPHRASE if item.get("role_paraphrase") else SYSTEME
    return [
        {"role": "system", "content": systeme},
        {"role": "user", "content": GABARIT.format(fragment=item["fragment"].strip(),
                                                   question=item["question"])},
    ]


if __name__ == "__main__":
    import json
    items = [json.loads(l) for l in open("campaign_items.jsonl", encoding="utf-8")]
    longueurs = [len(construire(i)[1]["content"]) for i in items]
    print(f"{len(items)} items")
    print(f"longueur du message utilisateur : min {min(longueurs)}  "
          f"max {max(longueurs)}  moyenne {sum(longueurs)//len(longueurs)} caracteres")
    print(f"estimation jetons entree : ~{sum(longueurs)//4:,} au total pour une passe")
    print(f"\n--- exemple ({items[0]['item_id']}) ---")
    m = construire(items[0])
    print(m[1]["content"][:700] + "\n[...]\n" + m[1]["content"][-620:])
