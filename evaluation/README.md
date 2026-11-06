# Evaluation material

* `MOMTC_v2_0_evaluated.ofn` — the exact ontology file on which the SPARQL verification and the
  LLM-assisted evaluation were run, i.e. MOMTC v2.0.0 before the revision of competency question CQ1
  (SHA-256 prefix `edc7d41fc0cd9036`). The published `MOMTC.owl` adds 24 axioms to it and removes none.
* `sparql_evaluated/CQ1.rq` — the query of CQ1 as executed on that file; the other 38 queries are
  unchanged and are those of `competency-questions/sparql/`.

## LLM-assisted evaluation (`llm/`)

### Data
* `code/campaign_items_full.jsonl` — the 179 evaluation items (competency question, ontology fragment,
  ground truth, condition). Field names are in French: `verite_terrain` = ground truth,
  `couverture` = natural or ablated item, `lexique` = vocabulary condition (`original`; `renomme` = C1a,
  fragment renamed; `renomme_q` = C1b, question and fragment renamed), `variante` = prompt variant
  (`base`, `paraphrase`, `reordre`, `revision_v11` = re-verification after the revision of CQ1; this is an internal label assigned during
  the campaign and kept unchanged in the raw log, the revision itself being part of MOMTC v2.0.0).
* `code/ablation_manifest.json` — the 12 ablated items and the element removed, rewired or substituted.
* `code/questions_renommees.csv` — the renamed competency questions (condition C1b).
* `code/01_cqs.csv`, `code/momtc_tbox_corrige.ofn`, `code/momtc_tbox_revised.ofn` — inputs used to build the
  fragments (competency questions; TBox of the evaluated ontology; TBox after the revision of CQ1).
* `code/sparql_verdicts.csv` — SPARQL verdicts at schema and instance level.
* `results/resultats_campagne.jsonl` — one JSON record per model call (model requested and served,
  provider, item, run, timestamp, raw response, token usage and cost).
* `results/analysis/` — parsed verdicts, metrics with confidence intervals, statistical tests,
  baselines, coded disagreements and the re-verification of CQ1.
* `results/article_values.json` — every value reported in the article.

### Code
The scripts are in `code/` (comments in French). Requirements: Python 3.10+, `numpy`, `scipy`, `pandas`,
`scikit-learn`, `matplotlib`.

* Re-running the campaign (`run_campaign.py`) requires an OpenRouter API key, read from the environment
  variable `OPENROUTER_API_KEY` or from a local file `cle_openrouter.txt`. **The key is never stored in
  this repository** (see `.gitignore`).
* Recomputing the reported values from the deposited log does not require any key:
  ```
  cd evaluation/llm/code
  python tables_article.py        # writes article/valeurs.json, identical to results/article_values.json
  ```
