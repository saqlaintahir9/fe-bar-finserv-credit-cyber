# Databricks notebook: Spark GBT + UC MLflow (no extra pip)

from pyspark.ml import Pipeline
from pyspark.ml.classification import GBTClassifier
from pyspark.ml.feature import VectorAssembler
import mlflow
import mlflow.spark

CATALOG = "fe_bar_meridian"
gold = spark.table(f"{CATALOG}.shared_risk.fused_features").na.fill(0)
feat = [
    "amount",
    "minutes_since_new_device_login",
    "geo_mismatch_flag",
    "failed_logins_1h",
    "recent_ato_label",
    "device_is_new",
]
asm = VectorAssembler(inputCols=feat, outputCol="features", handleInvalid="keep")
gbt = GBTClassifier(labelCol="fraud_label", featuresCol="features", maxIter=20, seed=42)
pipe = Pipeline(stages=[asm, gbt])
mlflow.set_registry_uri("databricks-uc")
with mlflow.start_run(run_name="fused_gbt_spark") as run:
    model = pipe.fit(gold)
    mlflow.spark.log_model(model, "model", registered_model_name=f"{CATALOG}.shared_risk.fused_fraud_gbt")
    print("run_id", run.info.run_id)
    print("uc_model", f"{CATALOG}.shared_risk.fused_fraud_gbt")
    demo = gold.filter("txn_id = 'TXN-DEMO-ATO'")
    demo.select("txn_id", "account_id", "amount", "reason_codes", "fraud_label").show(truncate=False)
