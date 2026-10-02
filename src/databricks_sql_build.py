#!/usr/bin/env python3
"""Run FE Bar SQL on e2-demo warehouse. Token from env DATABRICKS_TOKEN."""

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


def run(sql: str, timeout_s: int = 120) -> dict:
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
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
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
        raise RuntimeError(json.dumps(err, indent=2)[:2000])
    return data


STATEMENTS = [
    """CREATE OR REPLACE TABLE fe_bar_meridian.cyber.bronze_auth_events
AS SELECT * FROM read_files(
  '/Volumes/fe_bar_meridian/shared_risk/landing/auth_events/',
  format => 'csv',
  header => true,
  inferSchema => true
)""",
    """CREATE OR REPLACE TABLE fe_bar_meridian.credit.bronze_card_transactions
AS SELECT * FROM read_files(
  '/Volumes/fe_bar_meridian/shared_risk/landing/card_transactions/',
  format => 'csv',
  header => true,
  inferSchema => true
)""",
    """CREATE OR REPLACE TABLE fe_bar_meridian.credit.bronze_accounts
AS SELECT * FROM read_files(
  '/Volumes/fe_bar_meridian/shared_risk/landing/accounts/',
  format => 'csv',
  header => true,
  inferSchema => true
)""",
    """CREATE OR REPLACE TABLE fe_bar_meridian.cyber.silver_auth_events AS
SELECT
  CAST(event_id AS STRING) event_id,
  CAST(account_id AS STRING) account_id,
  to_timestamp(ts) event_ts,
  CAST(device_id AS STRING) device_id,
  CAST(device_is_new AS INT) device_is_new,
  CAST(ip_geo AS STRING) ip_geo,
  CAST(geo_is_new AS INT) geo_is_new,
  CAST(auth_result AS STRING) auth_result,
  CAST(failed_attempts_1h AS INT) failed_attempts_1h,
  CAST(mfa_used AS INT) mfa_used,
  CAST(ato_label AS INT) ato_label
FROM fe_bar_meridian.cyber.bronze_auth_events
WHERE account_id IS NOT NULL AND ts IS NOT NULL""",
    """CREATE OR REPLACE TABLE fe_bar_meridian.credit.silver_card_transactions AS
SELECT
  CAST(txn_id AS STRING) txn_id,
  CAST(account_id AS STRING) account_id,
  to_timestamp(ts) txn_ts,
  CAST(amount AS DOUBLE) amount,
  CAST(mcc AS STRING) mcc,
  CAST(merchant_country AS STRING) merchant_country,
  CAST(channel AS STRING) channel,
  CAST(pan_token AS STRING) pan_token,
  CAST(decision AS STRING) decision,
  CAST(fraud_label AS INT) fraud_label
FROM fe_bar_meridian.credit.bronze_card_transactions
WHERE txn_id IS NOT NULL AND account_id IS NOT NULL AND CAST(amount AS DOUBLE) > 0""",
    """CREATE OR REPLACE TABLE fe_bar_meridian.credit.silver_accounts AS
SELECT
  CAST(account_id AS STRING) account_id,
  to_date(open_date) open_date,
  CAST(credit_limit AS DOUBLE) credit_limit,
  CAST(segment AS STRING) segment,
  CAST(home_geo AS STRING) home_geo,
  CAST(email AS STRING) email,
  CAST(pan_token AS STRING) pan_token
FROM fe_bar_meridian.credit.bronze_accounts
WHERE account_id IS NOT NULL""",
    """CREATE OR REPLACE TABLE fe_bar_meridian.shared_risk.fused_features AS
WITH latest_auth AS (
  SELECT * FROM (
    SELECT
      a.*,
      row_number() OVER (PARTITION BY account_id ORDER BY event_ts DESC) rn
    FROM fe_bar_meridian.cyber.silver_auth_events a
  ) WHERE rn = 1
)
SELECT
  t.txn_id,
  t.account_id,
  t.txn_ts,
  t.amount,
  t.mcc,
  t.channel,
  t.decision,
  t.fraud_label,
  round((unix_timestamp(t.txn_ts) - unix_timestamp(a.event_ts)) / 60.0, 2) AS minutes_since_new_device_login,
  CASE WHEN a.ip_geo IS NOT NULL AND a.ip_geo <> c.home_geo THEN 1 ELSE 0 END AS geo_mismatch_flag,
  coalesce(a.failed_attempts_1h, 0) AS failed_logins_1h,
  coalesce(a.ato_label, 0) AS recent_ato_label,
  coalesce(a.device_is_new, 0) AS device_is_new,
  c.segment,
  concat_ws(',',
    CASE WHEN coalesce(a.device_is_new,0)=1
          AND (unix_timestamp(t.txn_ts) - unix_timestamp(a.event_ts))/60.0 <= 15
         THEN 'new_device_recent' END,
    CASE WHEN a.ip_geo IS NOT NULL AND a.ip_geo <> c.home_geo THEN 'geo_mismatch' END,
    CASE WHEN coalesce(a.failed_attempts_1h,0) >= 3 THEN 'failed_logins_burst' END,
    CASE WHEN coalesce(a.ato_label,0)=1 THEN 'ato_signal' END
  ) AS reason_codes
FROM fe_bar_meridian.credit.silver_card_transactions t
LEFT JOIN latest_auth a ON t.account_id = a.account_id
LEFT JOIN fe_bar_meridian.credit.silver_accounts c ON t.account_id = c.account_id""",
    """SELECT COUNT(*) gold_rows FROM fe_bar_meridian.shared_risk.fused_features""",
    """SELECT txn_id, account_id, amount, minutes_since_new_device_login, geo_mismatch_flag,
        failed_logins_1h, reason_codes, fraud_label
 FROM fe_bar_meridian.shared_risk.fused_features
 WHERE txn_id = 'TXN-DEMO-ATO'""",
]


def main() -> None:
    for i, sql in enumerate(STATEMENTS):
        preview = " ".join(sql.split())[:90]
        print(f"[{i}] {preview}...")
        data = run(sql)
        result = data.get("result", {})
        data_arr = result.get("data_array")
        if data_arr:
            print("    ", data_arr[:5])
    print("OK")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        print(e.read().decode()[:2000], file=sys.stderr)
        raise
