import h2o

h2o.init()

df = h2o.import_file("cga_train_500.csv")

print("Rows:", df.nrows)
print("Cols:", df.ncols)
print(df.head())
print(df.types)  # ดูชนิดข้อมูลแต่ละคอลัมน์

h2o.shutdown(prompt=False)
