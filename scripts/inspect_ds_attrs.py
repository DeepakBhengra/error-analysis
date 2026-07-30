"""Inspect orderType / isDirectShipOrder attribute values in samples."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

OUT = Path("results/order-type-ds-compare")
d_samples = json.loads((OUT / "d-samples.json").read_text(encoding="utf-8"))
s_samples = json.loads((OUT / "s-samples.json").read_text(encoding="utf-8"))
mixed = {"PONUK2017101"}
d_samples = [s for s in d_samples if s["customer_order_number"].upper() not in mixed]
s_samples = [s for s in s_samples if s["customer_order_number"].upper() not in mixed]


def attrs(req):
    out = {}
    for item in req.get("additionalAttributes") or []:
        if isinstance(item, dict) and item.get("attributeName"):
            out[str(item["attributeName"])] = str(item.get("attributeValue") or "")
    return out


def line_attr_names(req):
    names = Counter()
    dsc_names = Counter()
    for line in req.get("lines") or []:
        if not isinstance(line, dict):
            continue
        for item in line.get("additionalAttributes") or []:
            if isinstance(item, dict) and item.get("attributeName"):
                names[str(item["attributeName"])] += 1
        for item in line.get("directShipConfigAttributes") or []:
            if isinstance(item, dict) and item.get("attributeName"):
                dsc_names[str(item["attributeName"])] += 1
    return names, dsc_names


print("=== Header additionalAttributes orderType / isDirectShipOrder ===")
for label, samples in (("D", d_samples), ("S", s_samples)):
    print(f"\n-- {label} --")
    for s in samples:
        a = attrs(s["request"])
        print(
            f"  {s['customer_order_number']}: "
            f"orderType={a.get('orderType')!r} "
            f"isDirectShipOrder={a.get('isDirectShipOrder')!r} "
            f"ordersubtype={a.get('ordersubtype')!r} "
            f"orderdoctype={a.get('orderdoctype')!r}"
        )

print("\n=== D samples with costoverrideflag / directShipConfig ===")
for s in d_samples:
    req = s["request"]
    has_cost = False
    has_dsc = False
    dsc_example = None
    for line in req.get("lines") or []:
        if not isinstance(line, dict):
            continue
        for item in line.get("additionalAttributes") or []:
            if isinstance(item, dict) and str(item.get("attributeName") or "").lower() == "costoverrideflag":
                if str(item.get("attributeValue") or "").lower() == "true":
                    has_cost = True
        if line.get("directShipConfigAttributes"):
            has_dsc = True
            if dsc_example is None:
                dsc_example = {
                    "lineType": line.get("lineType"),
                    "vendorPartNumber": line.get("vendorPartNumber"),
                    "ingramPartNumber": line.get("ingramPartNumber"),
                    "dsc": line.get("directShipConfigAttributes")[:6],
                }
    print(f"  {s['customer_order_number']}: costoverride={has_cost} dsc={has_dsc}")
    if dsc_example:
        print(f"    eg: {json.dumps(dsc_example)}")

# Common mandatory intersection of all D that is NOT just shared with S
print("\n=== Fields in >=80% D (practical mandatory candidates) ===")
# reuse flatten from prior

def flatten(obj, prefix=""):
    paths = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else key
            if key in ("additionalAttributes", "vmfAdditionalAttributes", "directShipConfigAttributes") and isinstance(value, list):
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

d_stats = Counter()
s_stats = Counter()
for s in d_samples:
    d_stats.update(flatten(s["request"]))
for s in s_samples:
    s_stats.update(flatten(s["request"]))
n_d, n_s = len(d_samples), len(s_samples)
for path in sorted(d_stats):
    if d_stats[path] / n_d >= 0.8:
        sr = s_stats[path] / n_s
        print(f"  {path}: D={d_stats[path]/n_d:.0%} S={sr:.0%}")
