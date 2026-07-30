# D vs S attribute notes (39 + 39 prod SUCCESS samples)

Source: Datadog prod `uschileai1401–1404`, ~45 days ending 2026-07-29.  
Full tables: `ATTRIBUTE-REPORT-40.md` · raw: `attribute-comparison-40.json`, `d-samples-40.json`, `s-samples-40.json`.

## How to read this

- **D/S label** comes from the **response** (`orders[].orderType`), then we compare the matching **inbound v6 request**.
- Rates = share of samples where the attribute/field is present (non-empty).

---

## D-type specific attributes
Near-exclusive: **≥25% on D** and **≤10% on S**.

### Header `additionalAttributes`
| Attribute | D | S |
|---|---:|---:|
| `print` | 62% | 5% |
| `endusername` | 59% | 5% |
| `isSalesMan` | 59% | 8% |
| `provcontactemail` / `provcontactname` / `provcontactphone` | 46–49% | 5% |
| `carriercodeds` | 33% | 3% |
| `deliNotifEmail` | 33% | 3% |
| `campaign` | 28% | 3% |
| `resellerenduserid` | 26% | 0% |
| `ismigration` | 26% | 5% |

### Line `additionalAttributes`
| Attribute | D | S |
|---|---:|---:|
| `contractStartDate` / `contractEndDate` | 64% | 5% |
| `enduseremail` / `enduserphone` | 31% | 3% |

### Line fields / VMF / DSC
| Attribute | D | S |
|---|---:|---:|
| `lines[].specialBidNumber` | 36% | 8% |
| `lines[].acopTrackingNumber` | 28% | 8% |
| line VMF `prodmdlnumber` | 38% | 5% |
| line VMF `authBidNumber` | 33% | 3% |
| line VMF `newcontractflag` | 26% | 0% |
| DSC `zerodollarflag` | 26% | 0% |
| header VMF `shipCtacEmail` / `euShipCtacNam` | 31–33% | 5–8% |

---

## D-enriched (very strong, not fully exclusive)
Still the best practical D markers (**~74–80% D vs ~10% S**):

| Attribute / block | D | S |
|---|---:|---:|
| **`lines[].directShipConfigAttributes`** | **80%** | 10% |
| DSC: `vendornumber`, `stdcostamount`, `discountedcost`, `discountedprice` | 74% | 10% |
| **`isDirectShipOrder`** | **77%** | 10% |
| Header path cluster: `entryMethod`, `operatorId`, `orderdoctype`, `ordersubtype`, `orderrecordid`, `regionCode`, `thirdPartyFreightAccountNumber`, `euPoNumber`, … | ~74% | 10% |
| Line: `applicabletorenewal`, `tcc`, `tcv` | 74% | 10% |
| Top-level **`vmf`** | **82%** | 20% |
| `lines[].vendorParams`, `lines[].vmf` | 74% | 10% |

---

## S-type specific attributes
Near-exclusive: **≥25% on S** and **≤10% on D**.

| Attribute | D | S | Where |
|---|---:|---:|---|
| **`OrderMode`** | 5% | **31%** | header `additionalAttributes` |
| **`currencyCode`** | 3% | **26%** | top-level |

S has few *exclusive* attributes; stock orders are mostly defined by **absence of D markers**.

---

## S-enriched (common on S, uncommon on D)

| Attribute | D | S |
|---|---:|---:|
| `allowPartialOrder` / `capsbuyerid` / `continueonerror` / `entrymethod` / `operatorid` | ~26% | **90%** |
| `regioncode` | 23% | 80% |
| `basketid`, `delinotifemail` | 23% | 64% |
| `distributionchannel` / `division` / `salesorganization` | 20% | 56% |
| line `gsaflag` | 26% | **90%** |
| top-level **`billToAddressId`** | 28% | **92%** |
| `lines[].carrierCode` | 10% | 44% |
| `lines[].warrantyInfo` | 10% | 36% |
| line VMF reseller/ship contact block (`ResellerCompanyName`, `ShiptoAddress`, …) | ~13% | ~44% |

Note: D often uses camelCase (`entryMethod`, `operatorId`); S portal path often uses lowercase (`entrymethod`, `operatorid`) — same concepts, different client shapes.

---

## Shared (both ≥70%)

`customerOrderNumber`, `resellerInfo`, `shipToInfo`, `shipmentDetails`, `creditCardDetails`, `additionalAttributes`, `lines[]` with `customerLineNumber` / `quantity` / `vendorPartNumber` / `globalSkuId` / prices, `ordertotalvalue`, `allowDuplicateCustomerOrderNumber`.

---

## Practical checklist

**Likely D request if you see:**
1. `lines[].directShipConfigAttributes` (especially vendornumber + cost fields)
2. `additionalAttributes.isDirectShipOrder = true`
3. Header `vmf[]`
4. Contract dates / `carriercodeds` / `specialBidNumber` / provision contacts

**Likely S request if you see:**
1. `OrderMode` and/or populated `currencyCode`
2. Portal-style lowercase attrs (`entrymethod`, `operatorid`, `basketid`, `gsaflag`)
3. `billToAddressId` filled
4. **No** `directShipConfigAttributes` / `isDirectShipOrder=true` / rich DSC cost block
