import h2o
from h2o.automl import H2OAutoML

# 1) start / connect h2o
h2o.init()

# 2) load data
df = h2o.import_file("cga_train_1000.csv")

# 3) set target + features
y = "risk_binary"
ignore = ["patient_id", "encounter_date"]
x = [c for c in df.columns if c not in ignore + [y]]

# ensure classification
df[y] = df[y].asfactor()

# 4) split train/test
train, test = df.split_frame(ratios=[0.8], seed=42)

# 5) AutoML (ลองก่อน 5-10 นาที)
aml = H2OAutoML(
    max_runtime_secs=600,     # 10 นาที (ปรับได้)
    balance_classes=True,     # สำคัญสำหรับ risk
    seed=42
)
aml.train(x=x, y=y, training_frame=train)

# 6) leaderboard + best model
print("\n=== Leaderboard ===")
print(aml.leaderboard)

leader = aml.leader
print("\n=== Best model ===")
print(leader.model_id)

# 7) evaluate on test
perf = leader.model_performance(test)
print("\n=== Test Performance ===")
print(perf)

print("\n=== Confusion Matrix (test) ===")
print(perf.confusion_matrix())

# 8) predict sample
pred = leader.predict(test)
print("\n=== Prediction head ===")
print(pred.head())

# 9) save model
model_path = h2o.save_model(leader, path="./models", force=True)
print("\nSaved model to:", model_path)

# NOTE: ไม่ต้อง shutdown ก็ได้ ถ้าจะรันต่อขั้น 3
# h2o.cluster().shutdown()
