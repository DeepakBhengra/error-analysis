import json
from pathlib import Path

OUT = Path("results/order-type-ds-compare")
d = json.loads((OUT / "d-samples.json").read_text(encoding="utf-8"))
for po in ("TESTIFBID01", "167439"):
    s = next(x for x in d if x["customer_order_number"] == po)
    req = s["request"]
    print("=" * 60, po)
    print("top keys:", list(req.keys()))
    print(
        "header attrs:",
        [
            (a.get("attributeName"), a.get("attributeValue"))
            for a in (req.get("additionalAttributes") or [])
        ][:30],
    )
    print("vmf:", req.get("vmf"))
    eu = req.get("endUserInfo")
    print("endUserInfo keys:", list(eu.keys()) if isinstance(eu, dict) else None)
    for i, line in enumerate((req.get("lines") or [])[:4]):
        print(f" line{i} keys={list(line.keys())}")
        print(
            f"  lineType={line.get('lineType')} vpn={line.get('vendorPartNumber')} "
            f"ipn={line.get('ingramPartNumber')} sku={line.get('globalSkuId')}"
        )
        print(f"  dsc={line.get('directShipConfigAttributes')}")
        print(
            "  attrs=",
            [
                (a.get("attributeName"), a.get("attributeValue"))
                for a in (line.get("additionalAttributes") or [])
            ][:20],
        )
