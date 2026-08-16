# Struck

Every wildlife strike on an American aircraft reported to the FAA since 1990 — 352,419 records,
975 species, 2,788 airports — searchable by species, airport, altitude and the crew's own remarks.

Reporting is voluntary, so this is a census of *reports*, not of strikes. See
[methodology.html](methodology.html) before drawing conclusions from any airport count.

## Data

FAA publishes the whole database: <https://wildlife.faa.gov/assets/database_excel.zip> (rebuilt daily).

## Rebuild

```
curl -o database_excel.zip https://wildlife.faa.gov/assets/database_excel.zip
unzip database_excel.zip          # -> Public.xlsx
python3 -c "import openpyxl,csv; ..."   # convert to strikes.csv
python3 build_faa.py              # -> out_faa/, copy to data/
```
