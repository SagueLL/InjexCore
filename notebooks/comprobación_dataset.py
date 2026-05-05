import pandas as pd

df = pd.read_csv("data/raw/dataset_pro.csv")

print(df.head())
print(df.describe())
print(df["estado"].value_counts())