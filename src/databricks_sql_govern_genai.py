#!/usr/bin/env python3
"""UC masking/grants + AI_QUERY narratives for flagged demo cases."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

HOST = os.environ["DATABRICKS_HOST"].rstrip("/")
TOKEN = os.environ["DATABRICKS_TOKEN"]
WAREHOUSE = os.environ.get("WAREHOUSE_ID", "72255d4cf9534448")


def run(sql: str, timeout_s: int = 180) -> dict:
    body = json.dumps(
        {
            "statement": sql,
            "warehouse_id": WAREHOUSE,
            "wait_timeout": "50s",
            "disposition": "INLINE",
            "format": "JSON_ARRAY",
        }
    ).encode()
    req = urllib.request.Request(
        f"{HOST}/api/2.0/sql/statements/",
        data=body,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = json.loads(resp.read().decode())
    state = data.get("status", {}).get("state")
    stmt_id = data.get("statement_id")
    deadline = time.time() + timeout_s
    while state in {"PENDING", "RUNNING"} and time.time() < deadline:
        time.sleep(2)
        req2 = urllib.request.Request(
            f"{HOST}/api/2.0/sql/statements/{stmt_id}",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        with urllib.request.urlopen(req2, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode())
        state = data.get("status", {}).get("state")
    if state != "SUCCEEDED":
        err = data.get("status", {}).get("error", data)
        raise RuntimeError(json.dumps(err, indent=2)[:3000])
    return data


def rows(data: dict):
    return data.get("result", {}).get("data_array") or []


STATEMENTS = [
    """CREATE OR REPLACE FUNCTION fe_bar_meridian.shared_risk.mask_email(e STRING)
RETURNS STRING
RETURN CASE WHEN e IS NULL THEN NULL ELSE concat(left(e, 2), '***@***.invalid') END""",
    """CREATE OR REPLACE FUNCTION fe_bar_meridian.shared_risk.mask_pan(p STRING)
RETURNS STRING
RETURN CASE WHEN p IS NULL THEN NULL ELSE concat('tok_****', right(p, 4)) END""",
    """ALTER TABLE fe_bar_meridian.credit.silver_accounts ALTER COLUMN email SET MASK fe_bar_meridian.shared_risk.mask_email""",
    """ALTER TABLE fe_bar_meridian.credit.silver_accounts ALTER COLUMN pan_token SET MASK fe_bar_meridian.shared_risk.mask_pan""",
    """ALTER TABLE fe_bar_meridian.credit.silver_card_transactions ALTER COLUMN pan_token SET MASK fe_bar_meridian.shared_risk.mask_pan""",
    """ALTER TABLE fe_bar_meridian.credit.silver_accounts SET TAGS ('pii' = 'email', 'division' = 'credit')""",
    """ALTER TABLE fe_bar_meridian.cyber.silver_auth_events SET TAGS ('division' = 'cyber')""",
    """ALTER TABLE fe_bar_meridian.shared_risk.fused_features SET TAGS ('division' = 'shared')""",
    """SELECT privilege_type, grantee FROM fe_bar_meridian.information_schema.table_privileges
 WHERE table_schema = 'shared_risk' AND table_name = 'fused_features' LIMIT 30""",
    """SELECT account_id, email, pan_token FROM fe_bar_meridian.credit.silver_accounts WHERE account_id = 'ACC-100042'""",
    """CREATE OR REPLACE TABLE fe_bar_meridian.shared_risk.flagged_cases AS
SELECT
  txn_id,
  account_id,
  amount,
  reason_codes,
  AI_QUERY(
    'databricks-claude-sonnet-4',
    concat(
      'Write a 2-sentence SOC analyst narrative. Use ONLY these reason_codes and facts. Do not invent causes. This is not a legal adverse-action letter. Codes=',
      reason_codes,
      ' amount=', CAST(amount AS STRING),
      ' account=', account_id,
      ' minutes_since_new_device=', CAST(minutes_since_new_device_login AS STRING)
    )
  ) AS reason_narrative
FROM fe_bar_meridian.shared_risk.fused_features
WHERE txn_id = 'TXN-DEMO-ATO'""",
    """SELECT * FROM fe_bar_meridian.shared_risk.flagged_cases""",
]


def main() -> None:
    out = []
    for i, sql in enumerate(STATEMENTS):
        preview = " ".join(sql.split())[:100]
        print(f"[{i}] {preview}")
        try:
            data = run(sql)
            r = rows(data)
            print("    rows", r[:8] if r else "ok")
            out.append({"i": i, "sql": preview, "rows": r})
        except Exception as e:
            print("    FAIL", str(e)[:800])
            out.append({"i": i, "sql": preview, "error": str(e)[:800]})
    Path = __import__("pathlib").Path
    Path(__file__).resolve().parents[1].joinpath("docs/evidence/02_uc_grants.txt").write_text(
        json.dumps(out[:10], indent=2) + "\n"
    )
    Path(__file__).resolve().parents[1].joinpath("docs/evidence/04_genai_narratives.txt").write_text(
        json.dumps(out[10:], indent=2) + "\n"
    )


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        print(e.read().decode()[:2000], file=sys.stderr)
        raise
