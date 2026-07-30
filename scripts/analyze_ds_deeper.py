"""Deeper D vs S field-rate analysis on saved samples."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

OUT = Path("results/order-type-ds-compare")
d_samples = json.loads((OUT / "d-samples.json").read_text(encoding="utf-8"))
s_samples = json.loads((OUT / "s-samples.json").read_text(encoding="utf-8"))

# Drop POs that appear in both (mixed response order types)
d_pos = {s["customer_order_number"].upper() for s in d_samples}
s_pos = {s["customer_order_number"].upper() for s in s_samples}
mixed = d_pos & s_pos
print("Mixed POs excluded:", mixed)
d_samples = [s for s in d_samples if s["customer_order_number"].upper() not in mixed]
s_samples = [s for s in s_samples if s["customer_order_number"].upper() not in mixed]
print(f"D={len(d_samples)} {[s['customer_order_number'] for s in d_samples]}")
print(f"S={len(s_samples)} {[s['customer_order_number'] for s in s_samples]}")


def flatten(obj, prefix=""):
    paths = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else key
            if key in (
                "additionalAttributes",
                "vmfAdditionalAttributes",
                "directShipConfigAttributes",
            ) and isinstance(value, list):
                paths.add(path)
                for item in value:
                    if isinstance(item, dict):
                        name = str(item.get("attributeName") or "").strip()
                        if name:
                            paths.add(f"{path}[{name}]")
                continue
            if isinstance(value, (dict, list)):
                paths |= flatten(value, path)
            else:
                if value is None or (isinstance(value, str) and not str(value).strip()):
                    continue
                paths.add(path)
    elif isinstance(obj, list):
        paths.add(prefix)
        for item in obj[:12]:
            paths |= flatten(item, f"{prefix}[]")
    return paths


def has_nonempty(obj, dotted):
    """Return True if path exists with non-empty value (simple dotted, no [])."""
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    if cur is None:
        return False
    if isinstance(cur, str):
        return bool(cur.strip())
    if isinstance(cur, (list, dict)):
        return bool(cur)
    return True


d_stats = Counter()
s_stats = Counter()
for s in d_samples:
    d_stats.update(flatten(s["request"]))
for s in s_samples:
    s_stats.update(flatten(s["request"]))

n_d = len(d_samples)
n_s = len(s_samples)
rows = []
for path in sorted(set(d_stats) | set(s_stats)):
    d_rate = d_stats[path] / n_d
    s_rate = s_stats[path] / n_s
    rows.append((path, d_stats[path], d_rate, s_stats[path], s_rate, d_rate - s_rate))

print("\n=== Biggest positive deltas (D - S) ===")
for path, dc, dr, sc, sr, delta in sorted(rows, key=lambda r: -r[5])[:40]:
    print(f"  {path}: D={dr:.0%}({dc}/{n_d}) S={sr:.0%}({sc}/{n_s}) delta={delta:+.2f}")

print("\n=== Biggest negative deltas (more in S) ===")
for path, dc, dr, sc, sr, delta in sorted(rows, key=lambda r: r[5])[:20]:
    print(f"  {path}: D={dr:.0%}({dc}/{n_d}) S={sr:.0%}({sc}/{n_s}) delta={delta:+.2f}")

print("\n=== Present in ALL D ===")
for path, dc, dr, sc, sr, delta in sorted(rows):
    if dr == 1.0:
        print(f"  {path}: S={sr:.0%}")

# Per-sample structural checklist
checklist = [
    "endCustomerOrderNumber",
    "billToAddressId",
    "allowPartialOrder",
    "acceptBackOrder",
    "quoteNumber",
    "terms",
    "currencyCode",
    "resellerInfo",
    "shipToInfo",
    "endUserInfo",
    "creditCardDetails",
    "vmf",
    "vmfAdditionalAttributes",
    "shipmentDetails",
    "additionalAttributes",
    "lines",
]


def sample_flags(req):
    flags = {}
    for key in checklist:
        flags[key] = has_nonempty(req, key)
    # shipTo / endUser richness
    for section in ("shipToInfo", "endUserInfo", "resellerInfo"):
        sec = req.get(section) or {}
        if isinstance(sec, dict):
            flags[f"{section}.addressLine1"] = bool(str(sec.get("addressLine1") or "").strip())
            flags[f"{section}.companyName"] = bool(str(sec.get("companyName") or "").strip())
            flags[f"{section}.resellerId"] = bool(str(sec.get("resellerId") or "").strip())
    # line-level
    lines = req.get("lines") or []
    flags["any_directShipConfigAttributes"] = any(
        isinstance(l, dict) and l.get("directShipConfigAttributes") for l in lines
    )
    flags["any_lineType"] = any(isinstance(l, dict) and l.get("lineType") for l in lines)
    flags["any_ingramPartNumber"] = any(
        isinstance(l, dict) and str(l.get("ingramPartNumber") or "").strip() for l in lines
    )
    flags["any_vendorPartNumber"] = any(
        isinstance(l, dict) and str(l.get("vendorPartNumber") or "").strip() for l in lines
    )
    flags["any_globalSkuId"] = any(
        isinstance(l, dict) and str(l.get("globalSkuId") or "").strip() for l in lines
    )
    flags["any_costoverrideflag"] = False
    flags["any_enduserid"] = False
    flags["any_shipFromWareHouseId"] = False
    for line in lines:
        if not isinstance(line, dict):
            continue
        for item in line.get("additionalAttributes") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("attributeName") or "").lower()
            val = str(item.get("attributeValue") or "").strip()
            if name == "costoverrideflag" and val.lower() == "true":
                flags["any_costoverrideflag"] = True
            if name == "enduserid" and val:
                flags["any_enduserid"] = True
            if name == "shipfromwarehouseid" and val:
                flags["any_shipFromWareHouseId"] = True
    return flags


print("\n=== Structural presence rates ===")
d_flag = Counter()
s_flag = Counter()
for s in d_samples:
    d_flag.update({k: 1 for k, v in sample_flags(s["request"]).items() if v})
for s in s_samples:
    s_flag.update({k: 1 for k, v in sample_flags(s["request"]).items() if v})
all_keys = sorted(set(d_flag) | set(s_flag) | set(checklist))
for key in all_keys:
    dr = d_flag[key] / n_d
    sr = s_flag[key] / n_s
    mark = ""
    if dr >= 0.8 and sr <= 0.4:
        mark = "  << D-CHAR"
    elif dr == 1.0 and sr < 1.0:
        mark = "  << all-D"
    print(f"  {key}: D={dr:.0%} S={sr:.0%}{mark}")

# Dump one rich D and one sparse S example keys
print("\n=== Example D request top-level (PO113046 if present) ===")
for s in d_samples:
    if s["customer_order_number"] == "PO113046":
        req = s["request"]
        print("top keys:", list(req.keys()))
        line0 = (req.get("lines") or [None])[0]
        if isinstance(line0, dict):
            print("line0 keys:", list(line0.keys()))
            print("line0.directShipConfigAttributes:", json.dumps(line0.get("directShipConfigAttributes"), indent=2)[:800])
            print("line0.additionalAttributes sample:", json.dumps(line0.get("additionalAttributes"), indent=2)[:800])
        break

# Save refined comparison
refined = {
    "excluded_mixed": sorted(mixed),
    "d_orders": [s["customer_order_number"] for s in d_samples],
    "s_orders": [s["customer_order_number"] for s in s_samples],
    "deltas": [
        {
            "path": path,
            "d_count": dc,
            "d_rate": round(dr, 2),
            "s_count": sc,
            "s_rate": round(sr, 2),
            "delta": round(delta, 2),
        }
        for path, dc, dr, sc, sr, delta in sorted(rows, key=lambda r: -r[5])
    ],
    "structural": {
        key: {
            "d_rate": round(d_flag[key] / n_d, 2),
            "s_rate": round(s_flag[key] / n_s, 2),
        }
        for key in all_keys
    },
}
(OUT / "refined-comparison.json").write_text(
    json.dumps(refined, indent=2) + "\n", encoding="utf-8"
)
print("\nWrote refined-comparison.json")
