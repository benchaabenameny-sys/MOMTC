#!/usr/bin/env python3
"""Analyse des desaccords juge / verite terrain (Tables 6 et 7).

Unite d'analyse : le verdict majoritaire (K = 3) d'un modele sur un item, dans
les deux conditions de vocabulaire retenues pour l'analyse principale
(original et renomme_q). Le renommage du seul fragment est exclu : son effet
est explique a part (rupture du pont lexical question-schema).

Deux familles d'erreurs :
  - rejet d'une CQ saine (faux negatif)  : codes R1 a R7 ;
  - acceptation d'un item ablate (faux positif) : codes F1 a F3.

Le code est attribue par CQ et par cas a partir de faits verifiables dans le
fragment (presence des elements requis, axiomes de domaine et de codomaine,
structure de la requete SPARQL de reference), puis confronte a la raison
donnee par le juge (champ missing_element). La table CODAGE ci-dessous est le
codage lui-meme : elle est publiee telle quelle et doit etre relue par
l'auteur (codeur unique, a declarer comme limite).
"""
import csv, pathlib, sys
import pandas as pd

CODES = {
    "R1": ("Genuine schema limitation",
           "The requirement cannot be expressed with the TBox: the judge is right."),
    "R2": ("Instance-level information",
           "The schema supports the CQ, but the specific values (e.g. NIST controls, "
           "CIA impact types) are individuals that a TBox-only fragment does not show."),
    "R3": ("Multi-hop path not recognised",
           "Every required element is in the fragment and the path exists through an "
           "intermediate node; the judge asks for a direct link."),
    "R4": ("Implicit temporal representation",
           "History is represented by several dated assessments (non-functional "
           "property + has_assessment_date); the judge asks for an explicit "
           "versioning mechanism."),
    "R5": ("Direct property overlooked or misread",
           "The required property is in the fragment with matching domain and range; "
           "the judge reports it as missing or wrongly wired."),
    "R6": ("Inverse direction not traversed",
           "The property exists in the opposite direction; a query traverses it "
           "without difficulty."),
    "R7": ("Renaming artefact",
           "Occurs only under renomme_q and the judge's objection is about a word "
           "produced by the mechanical renaming of the question."),
    "F1": ("Domain/range not checked",
           "A2 rewiring: the judge accepts the property on its name although its "
           "domain no longer matches."),
    "F2": ("Broken chain not detected",
           "A1/A3: one link of a multi-hop path is removed or substituted; the judge "
           "lists the remaining elements as sufficient."),
    "F4": ("Semantically adjacent path accepted",
           "A1: the removed link leaves a neighbouring path that answers a weaker "
           "question (targeting instead of impact); the ablation is partly ambiguous "
           "and the item is excluded in a sensitivity analysis."),
    "F3": ("Unrelated property accepted as equivalent",
           "A3: the judge accepts a different property as fulfilling the requirement."),
}

# Codage. Cle : (cq, condition, lexique, modele court). Justification : fait
# verifiable sur le fragment ou la requete. Pour les rejets, la condition est
# « naturel ».
CODAGE = {
    # --- rejets de CQ saines ------------------------------------------------
    ("CQ1", "naturel", "*", "*"): ("R1",
        "No ordering of Sophistication_Level individuals in the TBox (no rank or "
        "ordinal data property): 'or higher' cannot be evaluated from the schema; "
        "the SPARQL query returns levels and the comparison is left to the reader."),
    ("CQ24", "naturel", "*", "*"): ("R2",
        "is_formalized_by: D3FEND_Countermeasure -> Security_Control; NIST SP 800-53 "
        "membership is carried by the Security_Control individuals."),
    ("CQ17", "naturel", "renomme_q", "deepseek"): ("R2",
        "has_impact_type: Threat_Impact -> Impact_Type and results_in: "
        "Temporal_Execution -> Threat_Impact present; C/I/A are Impact_Type individuals."),
    ("CQ12", "naturel", "*", "*"): ("R4",
        "has_risk_assessment (CVE -> Risk_Assessment, not functional) and "
        "has_assessment_date present: several dated assessments give the history."),
    ("CQ15", "naturel", "*", "*"): ("R3",
        "is_known_exploited is a data property of Risk_Assessment, reached through "
        "has_risk_assessment."),
    ("CQ19", "naturel", "*", "*"): ("R3",
        "has_criticality_weight is on Asset_Criticality_Level, reached through "
        "has_asset_criticality."),
    ("CQ20", "naturel", "*", "*"): ("R3",
        "Technique -exploits_weakness-> CWE <-exhibits_weakness- CVE "
        "-has_risk_assessment-> Risk_Assessment; the comparison is done in the query."),
    ("CQ25", "naturel", "*", "*"): ("R3",
        "tech_relates_to_artifact and cm_relates_to_artifact meet on "
        "D3FEND_Digital_Artifact (join on the shared artifact)."),
    ("CQ31", "naturel", "*", "*"): ("R3",
        "orchestrates -> campaign_employs -> exploits_weakness, all present; "
        "campaign_employs is the link the judge says is missing."),
    ("CQ37", "naturel", "original", "*"): ("R3",
        "generates_indicator (domain CVE or technique) -> IoC <- detects "
        "(Detection_Mechanism); the path goes through the indicator."),
    ("CQ37", "naturel", "renomme_q", "*"): ("R7",
        "The objection concerns 'designate', produced by renaming 'identify' in the "
        "question; the same path is present."),
    ("CQ38", "naturel", "*", "*"): ("R3",
        "orchestrates -> causes_impact -> impacts_asset, all present."),
    ("CQ7", "naturel", "*", "*"): ("R5",
        "has_vector_category: Attack_Vector -> Attack_Vector_Type is in the fragment."),
    ("CQ14", "naturel", "*", "*"): ("R5",
        "is_identified_by: CVE_Products -> CPE_Platform is in the fragment, with the "
        "domain and range the judge asks for."),
    ("CQ27", "naturel", "*", "*"): ("R5",
        "has_assigned_role: Targeted_Asset -> Organizational_Role is in the fragment."),
    ("CQ36", "naturel", "*", "*"): ("R6",
        "has_organizational_role: Human_Factor -> Organizational_Role; the question "
        "reads it from the role side."),
    ("CQ5", "naturel", "renomme_q", "*"): ("R7",
        "Objection about 'templates', produced by renaming 'patterns' in the question; "
        "is_behaviorally_similar_to (symmetric) is present."),
    ("CQ6", "naturel", "renomme_q", "*"): ("R7",
        "Objection about 'attach to', produced by renaming 'belong to'; "
        "is_part_of_technique: Sub-Technique -> Offensive_Techniques is present and "
        "never rejected under the original vocabulary."),
    # --- acceptations d'items ablates ---------------------------------------
    ("CQ4", "A2", "*", "*"): ("F1",
        "controls_infrastructure domain rewired to Sophistication_Level."),
    ("CQ9", "A2", "*", "*"): ("F1",
        "precedes_tactic domain rewired to Threat_Behavior."),
    ("CQ17", "A2", "*", "*"): ("F1",
        "has_impact_type domain rewired to Asset_Criticality_Level."),
    ("CQ12", "A3", "*", "*"): ("F2",
        "has_risk_assessment replaced by transitively_exhibits: the CVE -> "
        "Risk_Assessment link is gone."),
    ("CQ15", "A3", "*", "*"): ("F2",
        "has_risk_assessment replaced by exhibits_weakness: the CVE -> "
        "Risk_Assessment link is gone."),
    ("CQ37", "A1", "*", "*"): ("F2",
        "detects removed: no link from Detection_Mechanism to the indicators."),
    ("CQ38", "A1", "*", "*"): ("F4",
        "impacts_asset removed, but Threat_Campaign -has_temporal_execution-> "
        "Temporal_Execution -targets_asset-> Targeted_Asset remains: the judges cite "
        "targets_asset, which gives targeted assets, not the assets ultimately impacted."),
    ("CQ33", "A3", "*", "*"): ("F3",
        "exploits_human_factor replaced by provides_access_to; the judge cites "
        "exploits_weakness as fulfilling the requirement."),
}


def code_pour(cq, cond, lex, mod):
    for cle in ((cq, cond, lex, mod), (cq, cond, lex, "*"), (cq, cond, "*", mod),
                (cq, cond, "*", "*")):
        if cle in CODAGE:
            return CODAGE[cle]
    return None


def main():
    src = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "analyse/resultats_parses.csv")
    out = src.parent
    d = pd.read_csv(src)
    d = d[(d.variante == "base") & d.lexique.isin(["original", "renomme_q"])]
    lignes = []
    for (cq, cond, lex, mod), x in d.groupby(["cq_id", "condition", "lexique", "modele_demande"]):
        verite = int(x.verite_terrain.iloc[0])
        vote = int(x.verdict.mean() >= 0.5)
        if vote == verite:
            continue
        court = mod.split("/")[1].split("-")[0]
        c = code_pour(cq, cond, lex, court)
        if c is None:
            sys.exit(f"cas non code : {cq} {cond} {lex} {court}")
        r = x[x.verdict == vote].iloc[0]
        lignes.append({"cq_id": cq, "condition": cond, "lexique": lex, "modele": court,
                       "type_erreur": "faux negatif" if verite == 1 else "faux positif",
                       "code": c[0], "categorie": CODES[c[0]][0], "justification": c[1],
                       "raison_du_juge": str(r.element_manquant_predit if vote == 0
                                             else r.raisonnement)[:400],
                       "validation_auteur": ""})
    t = pd.DataFrame(lignes).sort_values(["type_erreur", "code", "cq_id", "lexique", "modele"])
    t.to_csv(out / "desaccords_codes.csv", index=False)

    # denominateurs
    n_sains = d[d.condition == "naturel"].groupby(["cq_id", "lexique", "modele_demande"]).ngroups
    n_abl = d[d.condition != "naturel"].groupby(["cq_id", "lexique", "modele_demande"]).ngroups
    print(f"jugements majoritaires : {n_sains} sur CQ saines, {n_abl} sur items ablates")
    for typ, n in (("faux negatif", n_sains), ("faux positif", n_abl)):
        s = t[t.type_erreur == typ]
        print(f"\n{typ} : {len(s)} / {n} ({len(s)/n:.1%})")
        tab = s.pivot_table(index=["code", "categorie"], columns="modele",
                            values="cq_id", aggfunc="count", fill_value=0)
        tab["total"] = tab.sum(axis=1)
        tab["CQ"] = s.groupby(["code", "categorie"]).cq_id.apply(
            lambda v: ", ".join(sorted(set(v), key=lambda q: int(q[2:]))))
        print(tab.to_string())
        tab.to_csv(out / f"table_desaccords_{'rejets' if typ == 'faux negatif' else 'acceptations'}.csv")
    print(f"\necrit : {out/'desaccords_codes.csv'}")


if __name__ == "__main__":
    main()
