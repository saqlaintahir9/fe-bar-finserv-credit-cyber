from __future__ import annotations

import json
import time

import mlflow
import mlflow.sklearn
import pandas as pd
from mlflow.models import infer_signature
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import confusion_matrix, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

CATALOG = "fe_bar_meridian"
SCHEMA = "shared_risk"
MODEL_NAME = f"{CATALOG}.{SCHEMA}.fused_fraud_gbm"
DEMO = "ACC-100042"
INSTANCE = "fe-bar-meridian"
DNS = "ep-floral-star-d1i8ynxt.database.us-west-2.cloud.databricks.com"


def train_and_register():
    gold = spark.table(f"{CATALOG}.{SCHEMA}.fused_features").toPandas()
    feat = [
        "amount",
        "minutes_since_new_device_login",
        "geo_mismatch_flag",
        "failed_logins_1h",
        "recent_ato_label",
        "device_is_new",
    ]
    X = gold[feat].fillna(0).astype("float64")
    y = gold["fraud_label"].astype(int)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
    clf = GradientBoostingClassifier(random_state=42)
    mlflow.set_registry_uri("databricks-uc")
    with mlflow.start_run(run_name="fused_gbm_v1") as run:
        clf.fit(Xtr, ytr)
        proba = clf.predict_proba(Xte)[:, 1]
        pred = (proba >= 0.5).astype(int)
        metrics = {
            "roc_auc": float(roc_auc_score(yte, proba)),
            "precision_at_0_5": float(precision_score(yte, pred, zero_division=0)),
            "recall_at_0_5": float(recall_score(yte, pred, zero_division=0)),
            "confusion_matrix": confusion_matrix(yte, pred).tolist(),
            "mlflow_run_id": run.info.run_id,
            "uc_model": MODEL_NAME,
        }
        mlflow.log_metrics(
            {k: metrics[k] for k in ("roc_auc", "precision_at_0_5", "recall_at_0_5")}
        )
        sig = infer_signature(Xtr, clf.predict_proba(Xtr)[:, 1])
        mlflow.sklearn.log_model(
            clf, "model", signature=sig, registered_model_name=MODEL_NAME
        )
        print("METRICS", json.dumps(metrics))
    return metrics


def lakebase_timings():
    import psycopg2
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    cred = w.api_client.do(
        "POST", "/api/2.0/database/credentials", body={"instance_names": [INSTANCE]}
    )
    token = cred["token"]
    user = w.current_user.me().user_name
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
    for _ in range(8):
        cur.execute("SELECT 1")
        cur.fetchone()
    times = []
    row = None
    for _ in range(80):
        t0 = time.perf_counter()
        cur.execute(
            "SELECT account_id, txn_id, risk_score FROM risk_scores WHERE account_id = %s",
            (DEMO,),
        )
        row = cur.fetchone()
        times.append((time.perf_counter() - t0) * 1000)
    conn.close()
    times.sort()
    out = {
        "lookup_ms_p50": round(times[len(times) // 2], 3),
        "lookup_ms_p99": round(times[int(len(times) * 0.99) - 1], 3),
        "min_ms": round(min(times), 3),
        "n": len(times),
        "row": list(row) if row else None,
        "where": "serverless_job_same_region_pk_lookup",
    }
    print("LAKEBASE", json.dumps(out))
    return out


if __name__ == "__main__":
    train_and_register()
    lakebase_timings()
