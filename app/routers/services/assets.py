import csv, json, os
from typing import List, Dict, Any

JSON_OUTPUT_PATH = "app/static/json/assets_transformed.json"

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

def _smart_delimiter_and_reader(fh) -> csv.DictReader:
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
    header_set = set(header)
    missing = [c for c in SCHEMA_BASE if c not in header_set]
    if missing:
        raise ValueError(f"Colonnes obligatoires manquantes: {', '.join(missing)}")
    # At least one of each group
    for gname, rng in GROUP_RANGES.items():
        if not any((f"{gname}{i}" in header_set) for i in rng):
            raise ValueError(f"Au moins une colonne requise pour {gname} (ex: {gname}1)")
    # No unknown columns except allowed group names
    allowed = set(SCHEMA_BASE)
    for g, rng in GROUP_RANGES.items():
        for i in rng:
            allowed.add(f"{g}{i}")
    unknown = [c for c in header if c not in allowed]
    if unknown:
        raise ValueError(f"Colonnes non autorisées: {', '.join(unknown)}")

def transform_csv_to_json(csv_path: str) -> str:
    """
    Lit un CSV 'fournisseur' et écrit le JSON final dans JSON_OUTPUT_PATH.
    - Groupes:
        hdd:     { "hdd1": "...", ... }
        network: { "embmac1": "...", "nic1": "...", ... }
    """
    rows_out: List[Dict[str, Any]] = []

    # utf-8-sig pour ignorer un éventuel BOM Excel
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = _smart_delimiter_and_reader(fh)
        header = reader.fieldnames or []
        # normalisation simple (strip + BOM déjà géré par utf-8-sig)
        header = [h.strip() for h in header]
        _validate_headers(header)

        for row in reader:
            # Clean values
            row = {k: _to_none(v) for k, v in row.items()}
            if _is_blank_row(row):
                continue

            obj: Dict[str, Any] = {}
            obj["hdd"] = {}
            obj["network"] = {}

            # Base fields
            for key in SCHEMA_BASE:
                obj[key] = row.get(key)

            # HDD group
            for i in GROUP_RANGES["HDD"]:
                col = f"HDD{i}"
                val = row.get(col)
                if val is not None:
                    obj["hdd"][f"hdd{i}"] = val

            # NIC + EMBMAC → network
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

            # optional: drop empty maps to keep JSON compact
            if not obj["hdd"]:
                obj["hdd"] = {}
            if not obj["network"]:
                obj["network"] = {}

            rows_out.append(obj)

    os.makedirs(os.path.dirname(JSON_OUTPUT_PATH), exist_ok=True)
    with open(JSON_OUTPUT_PATH, "w", encoding="utf-8") as out:
        json.dump(rows_out, out, ensure_ascii=False, indent=2)

    return JSON_OUTPUT_PATH
