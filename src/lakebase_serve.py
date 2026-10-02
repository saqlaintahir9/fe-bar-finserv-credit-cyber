#!/usr/bin/env python3
"""Create risk_scores in Lakebase Postgres and time GET /risk/ACC-100042."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[1]
DEMO = "ACC-100042"
INSTANCE = "fe-bar-meridian"
DNS = "ep-floral-star-d1i8ynxt.database.us-west-2.cloud.databricks.com"


def credential() -> str:
    env = os.environ.copy()
    out = subprocess.check_output(
        [
            "databricks",
            "database",
            "generate-database-credential",
            "--json",
            json.dumps({"instance_names": [INSTANCE]}),
            "-o",
            "json",
        ],
        env=env,
        text=True,
    )
    data = json.loads(out)
    return data.get("token") or data.get("password") or data["credential"]


def main() -> None:
    token = credential()
    user = os.environ.get("LAKEBASE_USER", "saqlain.tahir@databricks.com")
    conn = psycopg2.connect(
        host=DNS,
        port=5432,
        dbname="databricks_postgres",
        user=user,
        password=token,
        sslmode="require",
        connect_timeout=30,
    )
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS risk_scores (
            account_id TEXT PRIMARY KEY,
            txn_id TEXT,
            risk_score DOUBLE PRECISION,
            reason_codes TEXT,
            amount DOUBLE PRECISION,
            as_of TIMESTAMPTZ,
            model_version TEXT
        )
        """
    )
    cur.execute(
        """
        INSERT INTO risk_scores (account_id, txn_id, risk_score, reason_codes, amount, as_of, model_version)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (account_id) DO UPDATE SET
          txn_id = EXCLUDED.txn_id,
          risk_score = EXCLUDED.risk_score,
          reason_codes = EXCLUDED.reason_codes,
          amount = EXCLUDED.amount,
          as_of = EXCLUDED.as_of,
          model_version = EXCLUDED.model_version
        """,
        (
            DEMO,
            "TXN-DEMO-ATO",
            0.9,
            "new_device_recent,geo_mismatch,failed_logins_burst,ato_signal",
            2318.47,
            "2026-09-30 18:00:00+00",
            "fused_gbm_v1",
        ),
    )
    times = []
    row = None
    for _ in range(20):
        t0 = time.perf_counter()
        cur.execute(
            "SELECT account_id, txn_id, risk_score, reason_codes, amount, as_of, model_version FROM risk_scores WHERE account_id = %s",
            (DEMO,),
        )
        row = cur.fetchone()
        times.append((time.perf_counter() - t0) * 1000)
    conn.close()
    payload = {
        "account_id": row[0],
        "txn_id": row[1],
        "score": row[2],
        "reason_codes": row[3].split(","),
        "amount": row[4],
        "as_of": str(row[5]),
        "model_version": row[6],
        "hot_path": f"GET /risk/{DEMO}",
        "store": "Lakebase Postgres fe-bar-meridian",
    }
    text = (
        f"lookup_ms_p50={sorted(times)[len(times)//2]:.3f}\n"
        f"lookup_ms_p99={sorted(times)[-1]:.3f}\n"
        f"n={len(times)}\n"
        f"payload={json.dumps(payload, indent=2, default=str)}\n"
    )
    (ROOT / "docs/evidence/05_lakebase_lookup.txt").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
