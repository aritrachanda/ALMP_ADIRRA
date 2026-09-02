import pyodbc
from collections import OrderedDict
from pathlib import Path

_DIR = Path(__file__).resolve().parent

conn = pyodbc.connect(
    r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
    f'DBQ={_DIR / "DPM2.0.accdb"};'
)
cursor = conn.cursor()

query = """
SELECT
    tg.Name as TableGroupName,
    tv.Code as TableCode,
    tv.Name as TableName,
    tvc.cellcode as CellCode,
    c.NAME as CategoryName,
    i.NAME as ItemName,
    c.CategoryID,
    c.Description,
    vv.EndReleaseID,
    tvc.VariableVID,
    cc.PropertyID
FROM
    (((((((TableVersionCell AS tvc
    INNER JOIN VariableVersion AS vv ON tvc.VariableVID = vv.VariableVID)
    INNER JOIN ContextComposition AS cc ON vv.ContextID = cc.ContextID)
    INNER JOIN Item AS i ON cc.ItemID = i.ItemID)
    INNER JOIN PropertyCategory AS pc ON cc.PropertyID = pc.PropertyID)
    INNER JOIN Category AS c ON pc.CategoryID = c.CategoryID)
    INNER JOIN TableVersion AS tv ON tvc.TableVID = tv.TableVID)
    INNER JOIN TableGroupComposition AS tgc ON tgc.TableID = tv.TableID)
    INNER JOIN TableGroup AS tg ON tgc.TableGroupID = tg.TableGroupID
ORDER BY tvc.CellCode
"""

cursor.execute(query)
rows = cursor.fetchall()
print(f"Got {len(rows)} rows")

# Structure: group by table_group -> table_code/table_name -> cellcode -> items
# Row: TableGroupName[0], TableCode[1], TableName[2], CellCode[3],
#      CategoryName[4], ItemName[5], CategoryID[6], Description[7],
#      EndReleaseID[8], VariableVID[9], PropertyID[10]

data = OrderedDict()
for row in rows:
    tg_name = str(row[0]) if row[0] else ""
    tv_code = str(row[1]) if row[1] else ""
    tv_name = str(row[2]) if row[2] else ""
    cellcode = str(row[3]) if row[3] else ""
    cat_name = str(row[4]) if row[4] else ""
    item_name = str(row[5]) if row[5] else ""
    prop_id = row[10]

    if tg_name not in data:
        data[tg_name] = OrderedDict()
    if tv_code not in data[tg_name]:
        data[tg_name][tv_code] = {"name": tv_name, "cells": OrderedDict()}
    if cellcode not in data[tg_name][tv_code]["cells"]:
        data[tg_name][tv_code]["cells"][cellcode] = []
    data[tg_name][tv_code]["cells"][cellcode].append((prop_id, cat_name, item_name))

# Write YAML
with open(_DIR / "dpm2.0.yaml", "w", encoding="utf-8") as f:
    for tg_name, tables in data.items():
        f.write(f"table_group_name: {tg_name}\n")
        for tv_code, table_data in tables.items():
            tv_name = table_data["name"]
            f.write(f"  - table_code: {tv_code}\n")
            f.write(f"    table_name: {tv_name}\n")
            f.write(f"    cells:\n")
            for cellcode, items in table_data["cells"].items():
                # Sort by PropertyID and deduplicate
                items.sort(key=lambda x: (x[0] if x[0] is not None else 0))
                seen = set()
                names = []
                for prop, cat, name in items:
                    key = (prop, cat, name)
                    if key not in seen:
                        seen.add(key)
                        names.append(f"{cat} = {name}")
                items_str = " | ".join(names)
                f.write(f"      {cellcode}:\n")
                f.write(f"        - items: [{items_str}]\n")

cursor.close()
conn.close()
print(f"Done. Written to {_DIR / 'dpm2.0.yaml'}")
