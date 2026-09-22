import os

# Resolve path relative to this script
base_dir = os.path.dirname(os.path.abspath(__file__))
csv_path = os.path.join(base_dir, "..", "data", "cga_train_1000.csv")

h2o.init()

df = h2o.import_file(csv_path)

print("Rows:", df.nrows)
print("Cols:", df.ncols)
print(df.head())
print(df.types)  # ดูชนิดข้อมูลแต่ละคอลัมน์

h2o.shutdown(prompt=False)
