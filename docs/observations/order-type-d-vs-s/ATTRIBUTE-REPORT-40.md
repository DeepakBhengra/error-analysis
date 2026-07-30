# D vs S V6 request attributes (expanded sample)

- Window: `2026-06-14T10:40:19.838873Z` .. `2026-07-29T10:40:19.838873Z`
- D samples: **39** pure SUCCESS response orderType=D
- S samples: **39** pure SUCCESS response orderType=S
- Source: prod hosts `uschileai1401–1404` (`AsyncOrderCreate` / `OrderCreate_v6*`)

## Sample POs

**D:** 2571, PO113046, CNB6072412, 1514228, OC-Y26-393, BEST29.07.MAIL, PO-0448, TESTIFBID01, 167439, 4902, LCN202610071621, 4500119628, 66134816, GAR DONDI, 29178, 66134824, GB02PO00006891-1, PO9955203, TESTINBETA26.7.4-3, PO-4132, CLASSIC /02/26-27, P27914179, ORDER-1388906, 4519549623, 9270577-1, IBK/8126352, 45339706, 32021895, 16010068, PO-3032624-1, P10389, HEMEL SNOWCENTRE L, PON051276, PO775755, W242242, 00000762, BS2604325, 2664019899, 9270648

**S:** SERVIAP, 176902-0, 4500779705, P27901559, 24470, 4519549977, PO8035607-INT, 4700088087, M75Q+E14, NANDED PO, EKMK, CLTN, CHRY, TIRUR, PO49745, FBCC205409, ALPY, TVM1, TCRR, TCRP, PALA, 0007841228, PONUK2019117, TEST VR/V0 SE, ADOR, 464769, 2617, PO782393, BE2026104691, PONUK2019114, PONUK2019115, PONUK2019112, P27914212, 464747, PONUK2019105, PONUK2019102, P27914209, P27914205, P27914203

## D-type specific attributes

Present on ≥25% of D and ≤10% of S (exclusive / near-exclusive to D).

### `directShipConfigAttributes`

| Attribute | D rate | S rate | delta |
|---|---:|---:|---:|
| `zerodollarflag` | 26% | 0% | +26% |

### `header_additionalAttributes`

| Attribute | D rate | S rate | delta |
|---|---:|---:|---:|
| `print` | 62% | 5% | +56% |
| `endusername` | 59% | 5% | +54% |
| `isSalesMan` | 59% | 8% | +51% |
| `provcontactemail` | 49% | 5% | +44% |
| `provcontactname` | 49% | 5% | +44% |
| `provcontactphone` | 46% | 5% | +41% |
| `carriercodeds` | 33% | 3% | +31% |
| `deliNotifEmail` | 33% | 3% | +31% |
| `campaign` | 28% | 3% | +26% |
| `resellerenduserid` | 26% | 0% | +26% |
| `ismigration` | 26% | 5% | +20% |

### `line_additionalAttributes`

| Attribute | D rate | S rate | delta |
|---|---:|---:|---:|
| `contractEndDate` | 64% | 5% | +59% |
| `contractStartDate` | 64% | 5% | +59% |
| `enduseremail` | 31% | 3% | +28% |
| `enduserphone` | 31% | 3% | +28% |

### `line_fields`

| Attribute | D rate | S rate | delta |
|---|---:|---:|---:|
| `lines[].specialBidNumber` | 36% | 8% | +28% |
| `lines[].acopTrackingNumber` | 28% | 8% | +20% |

### `line_vmfAdditionalAttributes`

| Attribute | D rate | S rate | delta |
|---|---:|---:|---:|
| `prodmdlnumber` | 38% | 5% | +33% |
| `authBidNumber` | 33% | 3% | +31% |
| `newcontractflag` | 26% | 0% | +26% |

### `vmfAdditionalAttributes`

| Attribute | D rate | S rate | delta |
|---|---:|---:|---:|
| `shipCtacEmail` | 33% | 8% | +26% |
| `euShipCtacNam` | 31% | 5% | +26% |

## S-type specific attributes

Present on ≥25% of S and ≤10% of D (exclusive / near-exclusive to S).

### `header_additionalAttributes`

| Attribute | D rate | S rate | delta |
|---|---:|---:|---:|
| `OrderMode` | 5% | 31% | -26% |

### `top_level`

| Attribute | D rate | S rate | delta |
|---|---:|---:|---:|
| `currencyCode` | 3% | 26% | -23% |

## Enriched on D (not exclusive)

Higher on D by ≥25 points, but also appears on some S.

### `directShipConfigAttributes`

| Attribute | D rate | S rate | delta |
|---|---:|---:|---:|
| `discountedcost` | 74% | 10% | +64% |
| `discountedprice` | 74% | 10% | +64% |
| `stdcostamount` | 74% | 10% | +64% |
| `vendornumber` | 74% | 10% | +64% |

### `header_additionalAttributes`

| Attribute | D rate | S rate | delta |
|---|---:|---:|---:|
| `isDirectShipOrder` | 77% | 10% | +67% |
| `allowpartialorder` | 74% | 10% | +64% |
| `entryMethod` | 74% | 10% | +64% |
| `headerholdstatusflag` | 74% | 10% | +64% |
| `operatorId` | 74% | 10% | +64% |
| `orderType` | 74% | 10% | +64% |
| `orderdoctype` | 74% | 10% | +64% |
| `orderrecordid` | 74% | 10% | +64% |
| `ordersubtype` | 74% | 10% | +64% |
| `regionCode` | 74% | 10% | +64% |
| `thirdPartyFreightAccountNumber` | 74% | 10% | +64% |
| `euPoNumber` | 72% | 10% | +62% |
| `isbackorderflagallowed` | 64% | 10% | +54% |

### `line_additionalAttributes`

| Attribute | D rate | S rate | delta |
|---|---:|---:|---:|
| `applicabletorenewal` | 74% | 10% | +64% |
| `tcc` | 74% | 10% | +64% |
| `tcv` | 74% | 10% | +64% |

### `line_fields`

| Attribute | D rate | S rate | delta |
|---|---:|---:|---:|
| `lines[].directShipConfigAttributes` | 80% | 10% | +69% |
| `lines[].vendorParams` | 74% | 10% | +64% |
| `lines[].vmf` | 74% | 10% | +64% |
| `lines[].lineType` | 82% | 36% | +46% |
| `lines[].vmfAdditionalAttributes` | 85% | 51% | +33% |

### `top_level`

| Attribute | D rate | S rate | delta |
|---|---:|---:|---:|
| `vmf` | 82% | 20% | +62% |
| `endCustomerOrderNumber` | 90% | 46% | +44% |
| `acceptBackOrder` | 64% | 31% | +33% |

### `vmfAdditionalAttributes`

| Attribute | D rate | S rate | delta |
|---|---:|---:|---:|
| `resellerCtacEmail` | 80% | 51% | +28% |
| `rslrg360CtacName` | 80% | 51% | +28% |

## Enriched on S (not exclusive)

### `header_additionalAttributes`

| Attribute | D rate | S rate | delta |
|---|---:|---:|---:|
| `allowPartialOrder` | 26% | 90% | -64% |
| `capsbuyerid` | 26% | 90% | -64% |
| `continueonerror` | 26% | 90% | -64% |
| `entrymethod` | 26% | 90% | -64% |
| `operatorid` | 26% | 90% | -64% |
| `regioncode` | 23% | 80% | -56% |
| `basketid` | 23% | 64% | -41% |
| `delinotifemail` | 23% | 64% | -41% |
| `distributionchannel` | 20% | 56% | -36% |
| `division` | 20% | 56% | -36% |
| `salesorganization` | 20% | 56% | -36% |

### `line_additionalAttributes`

| Attribute | D rate | S rate | delta |
|---|---:|---:|---:|
| `gsaflag` | 26% | 90% | -64% |

### `line_fields`

| Attribute | D rate | S rate | delta |
|---|---:|---:|---:|
| `lines[].carrierCode` | 10% | 44% | -33% |
| `lines[].warrantyInfo` | 10% | 36% | -26% |

### `line_vmfAdditionalAttributes`

| Attribute | D rate | S rate | delta |
|---|---:|---:|---:|
| `ResellerComapnyAddress` | 13% | 44% | -31% |
| `ResellerCompanyName` | 13% | 44% | -31% |
| `ShiptoAddress` | 13% | 44% | -31% |
| `resellerCtacEmail` | 13% | 44% | -31% |
| `rslrg360CtacName` | 13% | 44% | -31% |
| `rslrg360CtacNbr` | 13% | 44% | -31% |
| `shipCtacEmail` | 13% | 44% | -31% |
| `shipCtacPhone` | 13% | 44% | -31% |
| `eushipctacnam` | 10% | 38% | -28% |

### `top_level`

| Attribute | D rate | S rate | delta |
|---|---:|---:|---:|
| `billToAddressId` | 28% | 92% | -64% |
| `allowPartialOrder` | 23% | 64% | -41% |

### `vmfAdditionalAttributes`

| Attribute | D rate | S rate | delta |
|---|---:|---:|---:|
| `ResellerComapnyAddress` | 13% | 44% | -31% |
| `ResellerCompanyName` | 13% | 44% | -31% |

## Common attributes (≥70% on both)

### `header_additionalAttributes`

| Attribute | D rate | S rate |
|---|---:|---:|
| `ordertotalvalue` | 100% | 100% |
| `allowDuplicateCustomerOrderNumber` | 97% | 85% |

### `line_fields`

| Attribute | D rate | S rate |
|---|---:|---:|
| `lines[].additionalAttributes` | 100% | 100% |
| `lines[].aucSelectionCost` | 100% | 100% |
| `lines[].endUserPrice` | 100% | 100% |
| `lines[].globalSkuId` | 100% | 100% |
| `lines[].quantity` | 100% | 100% |
| `lines[].specialPrice` | 100% | 100% |
| `lines[].unitPrice` | 100% | 100% |
| `lines[].ingramPartNumber` | 90% | 80% |
| `lines[].customerLineNumber` | 95% | 74% |
| `lines[].vendorPartNumber` | 97% | 74% |
| `lines[].endUserPoNumber` | 90% | 72% |

### `top_level`

| Attribute | D rate | S rate |
|---|---:|---:|
| `additionalAttributes` | 100% | 100% |
| `creditCardDetails` | 100% | 100% |
| `customerOrderNumber` | 100% | 100% |
| `lines` | 100% | 100% |
| `resellerInfo` | 100% | 100% |
| `shipToInfo` | 100% | 100% |
| `shipmentDetails` | 100% | 100% |
| `vmfAdditionalAttributes` | 92% | 72% |

## Notes

- Response `orders[].orderType` is D/S; inbound requests rarely set a meaningful `additionalAttributes.orderType`.
- D-specific markers concentrate in `directShipConfigAttributes` and related direct-ship / VMF cost fields.
- S-specific markers (if any) tend to be stock/warehouse / portal path fields rather than direct-ship config.
