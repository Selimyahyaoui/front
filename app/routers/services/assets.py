import os, csv, json
from typing import List, Dict, Any
from pathlib import Path

# Store the final JSON in /tmp by default (OCP-friendly, no root)
JSON_OUTPUT_PATH = os.getenv("JSON_OUTPUT_PATH", "/tmp/assets/json/assets_transformed.json")

SCHEMA_BASE = [
    "SerialNumber","CFCode","region","CfnName","CustomerNumber","ProcessorType",
    "NumberSocket","NumberCore","Model","CustomerName","CustomerAddress",
    "PostCode","Country","OrderNumber","PONumber","BmcMacAddress",
    "Memory","HBA","BOSS","PERC","NVME","GPU"
]
GROUP_RANGES = {
    "HDD": range(1, 13),     # HDD1..HDD12
    "NIC": range(1, 7),      # NIC1..NIC6
    "EMBMAC": range(1, 4),   # EMBMAC1..EMBMAC3
}
EMPTY_MARKERS = {"", "NA", "N/A", "NULL"}

def _to_none(v: Any):
    if v is None: return None
    s = str(v).strip()
    return None if s == "" or s.upper() in EMPTY_MARKERS else s

def _is_blank_row(row: Dict[str, Any]) -> bool:
    for _, v in row.items():
        if v is None: 
            continue
        s = str(v).strip()
        if s.upper() not in EMPTY_MARKERS and s != "":
            return False
    return True

def _smart_reader(fh) -> csv.DictReader:
    # detect delimiter from the first line; handle comma/semicolon/tab
    pos = fh.tell()
    first = fh.readline()
    fh.seek(pos)
    delim = ","
    if first.count(";") > first.count(","):
        delim = ";"
    elif first.count("\t") > max(first.count(","), first.count(";")):
        delim = "\t"
    return csv.DictReader(fh, delimiter=delim)

def _validate_headers(header: List[str]):
    header = [h.strip() for h in header]
    header_set = set(header)

    # must have all base columns
    missing = [c for c in SCHEMA_BASE if c not in header_set]
    if missing:
        raise ValueError(f"Colonnes obligatoires manquantes: {', '.join(missing)}")

    # must have at least one of each group
    for gname, rng in GROUP_RANGES.items():
        if not any(f"{gname}{i}" in header_set for i in rng):
            raise ValueError(f"Au moins une colonne requise pour {gname} (ex: {gname}1)")

    # forbid unknown columns (only base + groups are allowed)
    allowed = set(SCHEMA_BASE)
    for g, rng in GROUP_RANGES.items():
        for i in rng:
            allowed.add(f"{g}{i}")
    unknown = [c for c in header if c not in allowed]
    if unknown:
        raise ValueError(f"Colonnes non autorisées: {', '.join(unknown)}")

def transform_csv_to_json(csv_path: str) -> str:
    """
    Read vendor CSV and write compact JSON to JSON_OUTPUT_PATH.
    - HDD grouped under 'hdd': { "hdd1": "...", ... }
    - NIC+EMBMAC grouped under 'network': { "nic1": "...", "embmac1": "...", ... }
    """
    rows_out: List[Dict[str, Any]] = []

    # utf-8-sig eats possible BOM from Excel
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = _smart_reader(fh)
        header = reader.fieldnames or []
        _validate_headers(header)

        for row in reader:
            row = {k: _to_none(v) for k, v in row.items()}
            if _is_blank_row(row):
                continue

            obj: Dict[str, Any] = {"hdd": {}, "network": {}}

            # base fields as-is
            for key in SCHEMA_BASE:
                obj[key] = row.get(key)

            # HDD -> "hdd"
            for i in GROUP_RANGES["HDD"]:
                col = f"HDD{i}"
                val = row.get(col)
                if val is not None:
                    obj["hdd"][f"hdd{i}"] = val

            # NIC + EMBMAC -> "network"
            for i in GROUP_RANGES["NIC"]:
                col = f"NIC{i}"
                val = row.get(col)
                if val is not None:
                    obj["network"][f"nic{i}"] = val
            for i in GROUP_RANGES["EMBMAC"]:
                col = f"EMBMAC{i}"
                val = row.get(col)
                if val is not None:
                    obj["network"][f"embmac{i}"] = val

            rows_out.append(obj)

    out_path = Path(JSON_OUTPUT_PATH)
    out_path.parent.mkdir(parents=True, exist_ok=True)  # /tmp is writable
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(rows_out, f, ensure_ascii=False, indent=2)

    return str(out_path)
