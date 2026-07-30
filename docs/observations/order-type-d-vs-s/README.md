# Observation: Order Create v6 — D vs S attributes

**Date:** 2026-07-29  
**Sample:** 39 pure-D + 39 pure-S SUCCESS inbound requests from prod Datadog  
**Hosts:** `uschileai1401–1404` (`AsyncOrderCreate` / `OrderCreate_v6*`)  
**Window:** ~45 days ending 2026-07-29

## What this is

Production analysis of inbound Order Create **v6 request** attributes that correlate with response `orders[].orderType`:

| Response | Meaning |
|---|---|
| `D` | Direct ship |
| `S` | Stock / warehouse |

The inbound request usually does **not** set a meaningful `orderType`; Impulse assigns D/S from product/fulfillment path. These notes capture which **request** fields predict that outcome.

## Files in this folder

| File | Purpose |
|---|---|
| `D-S-ATTRIBUTE-NOTES.md` | Concise D-specific / S-specific / enriched attribute checklist |
| `ATTRIBUTE-REPORT-40.md` | Full presence-rate tables by category |
| `order-type-attrs-40.canvas.tsx` | Cursor canvas source (n=39 comparison UI) |
| `order-type-d-vs-s.canvas.tsx` | Earlier canvas (smaller sample / overview) |

Raw JSON samples (large) stay under `results/order-type-ds-compare/`:

- `d-samples-40.json` / `s-samples-40.json`
- `attribute-comparison-40.json`

Mining script: `scripts/mine_order_type_attrs_40.py`

## Runtime use in the app

The web **Order Create Curl** panel classifies the edited curl live using these signals:

- Implementation: `web/src/guessOrderType.ts`
- UI: `web/src/components/CurlEditor.tsx`

Open the live canvas from Cursor’s canvases folder (copy of the source is kept here for the repo):

`%USERPROFILE%\.cursor\projects\c-Error-analsysis\canvases\order-type-attrs-40.canvas.tsx`

## Quick checklist

**Likely D:** `directShipConfigAttributes`, `isDirectShipOrder=true`, header `vmf[]`, `contractStart/EndDate`, `carriercodeds`, `specialBidNumber`

**Likely S:** `OrderMode`, `currencyCode`, portal lowercase attrs (`entrymethod`, `operatorid`, `basketid`, `gsaflag`), `billToAddressId`, and **absence** of D markers
