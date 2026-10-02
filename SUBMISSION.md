# FE Bar submission pack

Fill the form from this page. Validators read **text** (repo + this deck file + `docs/evidence/*.txt`). Screenshots do not count.

## Form fields

| Field | Paste this |
|---|---|
| **GitHub repo** | https://github.com/saqlaintahir9/fe-bar-finserv-credit-cyber |
| **Presentation deck** | Attach **`DECK.txt`** (or `DECK.md`) from the repo root — the in-repo file alone is not enough if the form has a file upload |
| **Conversation ID** (optional cheating-flag follow-up) | `7fd057ef-878a-4184-aa40-7b2b3eb82a84` |
| **Customer / industry** | Synthetic **Meridian Bank** · Financial Services · card issuer |
| **Outcome** | Fraud-loss reduction **and** false-positive decline reduction |

## Do not submit

- The confidential mapping file (gitignored; not in this repo)
- Any live-account names, tickets, or real PANs
- Screenshot-only evidence

## Six-stage evidence (Build = this table)

| Stage | Text evidence |
|---|---|
| Lakeflow | `docs/evidence/01_lakeflow.txt` — SDP `meridian-fraud-risk` COMPLETED; `ACC-100042` in gold |
| Unity Catalog | `docs/evidence/02_uc_grants.txt` — masks, tags, App SP SELECT |
| ML | `docs/evidence/03_model_metrics.txt` — ROC-AUC, confusion matrix, UC model versions 3–4 READY, demo score **0.90** |
| GenAI | `docs/evidence/04_genai_narratives.txt` — 10 narratives grounded in `reason_codes` |
| Lakebase | `docs/evidence/05_lakebase_lookup.txt` — `GET /risk/ACC-100042` payload score 0.9 |
| Genie | `docs/evidence/06_genie_qa.txt` — NL → SQL → rows for ACC-100042 |
| App | `docs/evidence/07_app_case_queue.txt` — score 0.90, `fused_gbm_v1`, top features |
| Data | `docs/evidence/00_data_profile.txt` |
| Session | `docs/evidence/08_conversation_id.txt` |

Executed notebooks with text outputs: `notebooks/01`–`05`.

## Live prototype (workspace e2-demo-field-eng)

- Catalog: `fe_bar_meridian`
- App: https://fe-bar-meridian-cmd-1444828305810485.aws.databricksapps.com
- Genie: https://e2-demo-field-eng.cloud.databricks.com/genie/rooms/01f1be1c7bba135f8491305e4038c5f4
- UC model: `fe_bar_meridian.shared_risk.fused_fraud_gbm`
- Demo thread: **ACC-100042** / **TXN-DEMO-ATO** / score **0.90**

## Role-play

Use `docs/roleplay_prep.md`. Open on ACC-100042. Lead with loss bps + FP rate; close technical answers with the business consequence.
