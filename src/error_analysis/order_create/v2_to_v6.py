"""Order Create v2 to v6 request body conversion.

Converts a legacy Order Create v2 request payload
(``{"ordercreaterequest": {...}}``) into a reseller Order Create v6
request body suitable for POSTing to ``/resellers/v6/orders``.

Two payload shapes are produced (learned from Datadog v2/v6 pairs):

**Simple portal** (no ``basketid``, no ``billtosuffix``, no header ``vmf``):
sparse lines (``customerLineNumber`` / ``ingramPartNumber`` / ``quantity``),
``enableCommentsAsLines`` + ``allowOrderOnCustomerHold`` defaults, and a
small ``additionalAttributes`` allow-list.

**Rich quote/ERP** (``basketid`` and/or ``billtosuffix`` and/or header
``vmf``): full field mapping including ``shipToInfo``, ``vmf``,
``shipmentDetails``, rich line fields, and broad attribute passthrough.

``requestpreamble.isocountrycode`` / ``customernumber`` and the ``IM-*``
extended specs become HTTP headers in v6; use
``error_analysis.order_create.curl_builder.build_order_create_headers``.
"""

from __future__ import annotations

from typing import Any

# v2 creditcarddetails key -> v6 creditCardDetails key
CREDIT_CARD_FIELD_MAP: dict[str, str] = {
    "creditcardnumber": "cardNumber",
    "paymentcode": "paymentCode",
    "cardtype": "cardType",
    "expirationdate": "expirationDate",
    "securitycode": "securityCode",
    "firstname": "firstName",
    "lastname": "lastName",
    "authorizationcode": "authorizationCode",
    "address": "address",
    "city": "city",
    "state": "state",
    "postalcode": "postalCode",
}

# Header extendedspecs that never reach the v6 body.
HEADER_SPECS_DROPPED: frozenset[str] = frozenset(
    {
        "isasync",
        "rslrctacemailind",
        "callingapplication",
        "isdirectshiporder",
        "isgdsapiinvoked",
        "orderdoctype",
        "rslrg360ctacnbr",
    }
)

# Header extendedspecs consumed by dedicated v6 fields (lowercase names).
HEADER_SPECS_CONSUMED: frozenset[str] = frozenset(
    {
        "signaturerequired",
        "duplicatecustomerordernumbervalidate",
        "resellerid",
    }
)

# Header extendedspecs routed to top-level vmfAdditionalAttributes.
HEADER_SPECS_TO_VMF: dict[str, str] = {
    "shipctacphone": "shipctacphone",
    "eushipctacnam": "eushipctacnam",
    "shipctacemail": "shipctacemail",
    "contractnumber": "contractNumber",
}

# Simple-mode additionalAttributes that always pass through when present.
SIMPLE_ATTR_ALLOWLIST: frozenset[str] = frozenset(
    {
        "eudepid",
        "depordernbr",
    }
)
# Extra simple-mode attrs kept only when entrymethod is XWEB.
SIMPLE_ATTR_XWEB_ALLOWLIST: frozenset[str] = frozenset(
    {
        "entrymethod",
        "operatorid",
        "capsbuyerid",
    }
)

# Line productextendedspecs dropped in rich mode (not present on actual v6).
LINE_SPECS_DROPPED: frozenset[str] = frozenset(
    {
        "everestflag",
        "vendorcode",
        "isdirectship",
        "mediacode",
        "iniswitch",
    }
)

# EU comment key (from "KEY: value" commenttext specs) -> endUserInfo field.
EU_COMMENT_FIELD_MAP: dict[str, str] = {
    "EUNAME": "companyName",
    "EUNAME1": "name1",
    "EUADD1": "addressLine1",
    "EUADD2": "addressLine2",
    "EUADD3": "addressLine3",
    "EUPH": "phoneNumber",
    "EUEMAIL": "email",
}

# v2 header vmf key -> v6 vmf entry key.
VMF_FIELD_MAP: dict[str, str] = {
    "quotenumber": "quoteNumber",
    "vendauthnumber": "vendAuthNumber",
    "csnumber": "csnNumber",
    "vendornumber": "vendorNumber",
}

# v2 line field -> v6 line field (rich mode).
LINE_FIELD_MAP: dict[str, str] = {
    "globalskuid": "globalSkuId",
    "ingrampartnumber": "ingramPartNumber",
    "vendorpartnumber": "vendorPartNumber",
    "enduserponumber": "endUserPoNumber",
    "carriercode": "carrierCode",
    "acoptrackingnumber": "acopTrackingNumber",
}

# productextendedspecs consumed by dedicated line fields/sections.
LINE_SPECS_CONSUMED: frozenset[str] = frozenset(
    {
        "aucselectioncost",
        "prodmdlnumber",
        "enduseremail",
        "enduserphone",
        "unitpriceswitch",
    }
)

# productextendedspecs passthrough renames (lowercase -> v6 spelling).
LINE_SPEC_RENAME: dict[str, str] = {
    "authbidnumber": "authBidNumber",
    "isheadervmfmissing": "isHeaderVMFMissing",
    "islinevmfmissing": "isLineVMFMissing",
}


class OrderCreateV2ToV6Error(ValueError):
    """Raised when a v2 payload cannot be converted to a v6 body."""


def _order_create_details(v2_request: dict[str, Any]) -> dict[str, Any]:
    """Return ordercreatedetails from a full or partial v2 payload."""
    if not isinstance(v2_request, dict):
        raise OrderCreateV2ToV6Error("v2 request must be a JSON object.")
    node = v2_request
    if isinstance(node.get("ordercreaterequest"), dict):
        node = node["ordercreaterequest"]
    if isinstance(node.get("ordercreatedetails"), dict):
        node = node["ordercreatedetails"]
    if "customerponumber" not in node:
        raise OrderCreateV2ToV6Error(
            "v2 payload is missing ordercreatedetails.customerponumber."
        )
    return node


def _clean_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _spec_pairs(specs: Any) -> list[tuple[str, str]]:
    """Extract (attributename, attributevalue) pairs with non-empty values.

    Adjacent ``commenttext`` fragments that look like wrap continuations
    (short values without ``:``) are concatenated onto the previous
    commenttext. Empirically ``PH: 716633360`` + ``0`` becomes
    ``PH: 7166333600`` on the v6 body.
    """
    pairs: list[tuple[str, str]] = []
    if not isinstance(specs, list):
        return pairs
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        name = spec.get("attributename")
        value = spec.get("attributevalue")
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(value, str) or not value.strip():
            continue
        name = name.strip()
        value = value.strip()
        if (
            pairs
            and name.lower() == "commenttext"
            and pairs[-1][0].lower() == "commenttext"
            and ":" not in value
            and len(value) <= 4
        ):
            prev_name, prev_value = pairs[-1]
            pairs[-1] = (prev_name, prev_value + value)
            continue
        pairs.append((name, value))
    return pairs


def _split_eu_comment(value: str) -> tuple[str, str] | None:
    """Split 'EUNAME: some value' into ('EUNAME', 'some value')."""
    key, sep, text = value.partition(":")
    key = key.strip().upper()
    if not sep or not key.startswith("EU"):
        return None
    return key, text.strip()


def _convert_quantity(value: Any) -> Any:
    """v2 uses floats (1.0); v6 expects integers when whole."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            as_float = float(value)
        except ValueError:
            return value
        return int(as_float) if as_float.is_integer() else as_float
    return value


def _convert_phone_number(value: Any) -> Any:
    """Line-level endUserInfo carries phoneNumber as a JSON number."""
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return value


def _to_bool(value: str) -> bool:
    return value.strip().upper() in {"Y", "YES", "TRUE"}


def _company_name_from_email(email: str) -> str:
    """Derive a display company name from the email domain (simple mode)."""
    _, _, domain = email.partition("@")
    label = domain.split(".")[0] if domain else ""
    return label.capitalize()


def _entrymethod(specs: list[tuple[str, str]]) -> str:
    return next(
        (value for name, value in specs if name.lower() == "entrymethod"),
        "",
    ).upper()


def _is_sap_mode(details: dict[str, Any], specs: list[tuple[str, str]]) -> bool:
    """SAP/ERP returns (ZWEB/ZCRM/…) — distinct from basket/quote rich mode."""
    entry = _entrymethod(specs)
    if entry.startswith("Z"):
        return True
    if _clean_str(details.get("currencycode")):
        return True
    if _clean_str(details.get("ordertype")):
        return True
    return False


def _is_rich_mode(details: dict[str, Any], specs: list[tuple[str, str]]) -> bool:
    """Basket/quote rich shape (not SAP, not sparse portal)."""
    if _is_sap_mode(details, specs):
        return False
    if _clean_str(details.get("billtosuffix")):
        return True
    if _clean_str(details.get("shiptosuffix")):
        return True
    vmf = details.get("vmf")
    if isinstance(vmf, dict) and any(
        _clean_str(vmf.get(key)) for key in VMF_FIELD_MAP
    ):
        return True
    for name, _value in specs:
        if name.lower() in {"basketid", "quoteid", "quotenumber", "quoteguid"}:
            return True
        if name == "quoteNumber":
            return True
    return False


def _convert_credit_card(details: dict[str, Any]) -> dict[str, Any] | None:
    source = details.get("creditcarddetails")
    if not isinstance(source, dict):
        return None
    converted = {
        v6_key: _clean_str(source.get(v2_key))
        for v2_key, v6_key in CREDIT_CARD_FIELD_MAP.items()
    }
    converted["authorizationAmount"] = ""
    return converted


def _convert_vmf(details: dict[str, Any]) -> list[dict[str, Any]] | None:
    source = details.get("vmf")
    if not isinstance(source, dict):
        return None
    entry: dict[str, Any] = {}
    for v2_key, v6_key in VMF_FIELD_MAP.items():
        value = _clean_str(source.get(v2_key))
        if value:
            entry[v6_key] = value
    vmfspecs = [
        {"attributeName": name, "attributeValue": value}
        for name, value in _spec_pairs(source.get("vmfspecs"))
    ]
    if vmfspecs:
        entry["vmfspecs"] = vmfspecs
    if not entry:
        return None
    return [entry]


def _convert_line_end_user(
    enduser: Any, *, always_emit: bool
) -> list[dict[str, Any]] | None:
    info: dict[str, Any] = {}
    if isinstance(enduser, dict):
        contact = _clean_str(enduser.get("name1"))
        phone = _clean_str(enduser.get("phonenumber"))
        email = _clean_str(enduser.get("email"))
        if contact:
            info["contact"] = contact
        if phone:
            info["phoneNumber"] = _convert_phone_number(phone)
        if email:
            info["email"] = email
    if info:
        return [info]
    if always_emit:
        return [{}]
    return None


def _convert_line_simple(line: dict[str, Any]) -> dict[str, Any]:
    converted: dict[str, Any] = {}
    line_number = _clean_str(line.get("linenumber"))
    if line_number:
        converted["customerLineNumber"] = line_number
    part = _clean_str(line.get("ingrampartnumber"))
    if part:
        converted["ingramPartNumber"] = part
    if "quantity" in line:
        converted["quantity"] = _convert_quantity(line.get("quantity"))
    if "unitprice" in line and line.get("unitprice") not in (None, ""):
        converted["unitPrice"] = line.get("unitprice")
    end_user = _convert_line_end_user(line.get("enduser"), always_emit=False)
    if end_user is not None:
        converted["endUserInfo"] = end_user
    return converted


def _convert_line_sap(line: dict[str, Any]) -> dict[str, Any]:
    """SAP lines keep ingramPartNumber (not globalSkuId) and skip specialPrice."""
    converted: dict[str, Any] = {}
    line_number = _clean_str(line.get("linenumber"))
    if line_number:
        converted["customerLineNumber"] = line_number
    part = _clean_str(line.get("ingrampartnumber"))
    if part:
        converted["ingramPartNumber"] = part
    vendor = _clean_str(line.get("vendorpartnumber"))
    if vendor:
        converted["vendorPartNumber"] = vendor
    if "quantity" in line:
        converted["quantity"] = _convert_quantity(line.get("quantity"))
    if "unitprice" in line and line.get("unitprice") not in (None, ""):
        converted["unitPrice"] = line.get("unitprice")

    specs = _spec_pairs(line.get("productextendedspecs"))
    attributes: list[dict[str, str]] = []
    for name, value in specs:
        lower = name.lower()
        if lower in LINE_SPECS_CONSUMED or lower in LINE_SPECS_DROPPED:
            continue
        if lower.startswith("im-"):
            continue
        attributes.append({"attributeName": name, "attributeValue": value})
    if attributes:
        converted["additionalAttributes"] = attributes
    return converted


def _convert_line_rich(
    line: dict[str, Any], *, has_basket: bool = False
) -> dict[str, Any]:
    converted: dict[str, Any] = {}
    line_number = _clean_str(line.get("linenumber"))
    if line_number:
        converted["customerLineNumber"] = line_number

    for v2_key, v6_key in LINE_FIELD_MAP.items():
        # Rich portal bodies use globalSkuId / vendorPartNumber; ingramPartNumber
        # is omitted even when present on the v2 line.
        if v2_key == "ingrampartnumber":
            continue
        value = _clean_str(line.get(v2_key))
        if value:
            converted[v6_key] = value

    if "quantity" in line:
        converted["quantity"] = _convert_quantity(line.get("quantity"))
    if "unitprice" in line:
        converted["unitPrice"] = line.get("unitprice")
        converted["specialPrice"] = "0"
    if "enduserprice" in line:
        converted["endUserPrice"] = line.get("enduserprice")

    specs = _spec_pairs(line.get("productextendedspecs"))

    for name, value in specs:
        if name.lower() == "aucselectioncost":
            try:
                converted["aucSelectionCost"] = float(value)
            except ValueError:
                converted["aucSelectionCost"] = value
            break

    vmf_attrs = [
        {"attributeName": "prodmdlnumber", "attributeValue": value}
        for name, value in specs
        if name.lower() == "prodmdlnumber"
    ]
    if vmf_attrs:
        converted["vmfAdditionalAttributes"] = vmf_attrs

    attributes: list[dict[str, str]] = []
    warehouse = _clean_str(line.get("warehouseid"))
    if warehouse:
        attributes.append(
            {"attributeName": "shipFromWareHouseId", "attributeValue": warehouse}
        )
    seen_attr_names: set[str] = set()
    for name, value in specs:
        lower = name.lower()
        if lower in LINE_SPECS_CONSUMED or lower in LINE_SPECS_DROPPED:
            continue
        if lower.startswith("im-"):
            continue
        if lower == "lcnsgsrvnumber":
            continue  # routed to vmfAdditionalAttributes below
        # Drop VMF-missing flags when true (actual v6 only keeps false).
        if lower in {"isheadervmfmissing", "islinevmfmissing"} and value.lower() == "true":
            continue
        attr_name = LINE_SPEC_RENAME.get(lower, name)
        # First occurrence wins for non-repeatable attrs (isHeaderVMFMissing).
        # commenttext may appear multiple times and must all be kept.
        if attr_name != "commenttext" and attr_name in seen_attr_names:
            continue
        seen_attr_names.add(attr_name)
        attributes.append(
            {"attributeName": attr_name, "attributeValue": value}
        )
    if attributes:
        converted["additionalAttributes"] = attributes

    license_attrs = [
        {"attributeName": "lcnsgsrvnumber", "attributeValue": value}
        for name, value in specs
        if name.lower() == "lcnsgsrvnumber"
    ]
    if license_attrs:
        existing = converted.get("vmfAdditionalAttributes")
        if isinstance(existing, list):
            converted["vmfAdditionalAttributes"] = existing + license_attrs
        else:
            converted["vmfAdditionalAttributes"] = license_attrs

    # Empty specialBidNumber on basket product lines with a non-zero unit price.
    # Zero-price / warranty / VMF-extended lines omit it.
    iniswitch = next(
        (value for name, value in specs if name.lower() == "iniswitch"), ""
    ).upper()
    mediacode = next(
        (value for name, value in specs if name.lower() == "mediacode"), ""
    ).upper()
    is_warranty = iniswitch == "W" or mediacode == "SVCS"
    unit_price = line.get("unitprice")
    has_nonzero_price = unit_price not in (None, "", 0, 0.0)
    if has_basket and not is_warranty and has_nonzero_price:
        converted["specialBidNumber"] = ""

    if is_warranty:
        converted["warrantyInfo"] = {}
    end_user = _convert_line_end_user(line.get("enduser"), always_emit=False)
    if end_user is not None:
        converted["endUserInfo"] = end_user
    elif (
        not is_warranty
        and "enduser" in line
        and _clean_str(line.get("acoptrackingnumber"))
    ):
        converted["endUserInfo"] = [{}]
    return converted


def _convert_lines(
    details: dict[str, Any],
    *,
    rich: bool,
    sap: bool = False,
    has_basket: bool = False,
) -> list[dict[str, Any]]:
    lines = details.get("lines")
    if not isinstance(lines, list):
        return []
    converted: list[dict[str, Any]] = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        line_type = _clean_str(line.get("linetype")).upper()
        if line_type and line_type != "P":
            continue
        if sap:
            converted.append(_convert_line_sap(line))
        elif rich:
            converted.append(_convert_line_rich(line, has_basket=has_basket))
        else:
            converted.append(_convert_line_simple(line))
    return converted


def _reseller_email(specs: list[tuple[str, str]]) -> str | None:
    emails = [value for name, value in specs if name.lower() == "resellerctacemail"]
    if emails:
        return emails[0]
    return next(
        (value for name, value in specs if name.lower() == "rslrctacemailind"),
        None,
    )


def convert_v2_to_v6(
    v2_request: dict[str, Any],
    *,
    notes: str = "",
    bill_to_address_id: str | None = None,
) -> dict[str, Any]:
    """Convert an Order Create v2 request payload to a v6 request body.

    ``notes`` has no v2 source and is omitted unless provided.
    ``bill_to_address_id`` overrides the v2 ``billtosuffix`` when given.
    """
    details = _order_create_details(v2_request)

    customer_order_number = _clean_str(details.get("customerponumber"))
    if not customer_order_number:
        raise OrderCreateV2ToV6Error(
            "ordercreatedetails.customerponumber is required."
        )

    specs = _spec_pairs(details.get("extendedspecs"))
    sap = _is_sap_mode(details, specs)
    rich = _is_rich_mode(details, specs)

    body: dict[str, Any] = {"customerOrderNumber": customer_order_number}

    end_customer = _clean_str(details.get("enduserordernumber"))
    if end_customer:
        body["endCustomerOrderNumber"] = end_customer

    if bill_to_address_id is not None:
        body["billToAddressId"] = bill_to_address_id
    else:
        body["billToAddressId"] = _clean_str(details.get("billtosuffix"))

    currency = _clean_str(details.get("currencycode")) or next(
        (value for name, value in specs if name.lower() == "currency"), ""
    )
    if sap and currency:
        body["currencyCode"] = currency

    continue_on_error = next(
        (value for name, value in specs if name.lower() == "continueonerror"),
        None,
    )
    allow_partial: str | None = None
    if sap:
        allow_partial = "true"
        body["allowPartialOrder"] = allow_partial
    elif rich and continue_on_error is not None and continue_on_error.upper() == "N":
        allow_partial = "false"
        body["allowPartialOrder"] = allow_partial

    quote_number = next(
        (value for name, value in specs if name == "quoteNumber"), None
    )
    if quote_number is not None:
        body["quoteNumber"] = quote_number

    if notes.strip():
        body["notes"] = notes.strip()

    reseller_info: dict[str, str] = {}
    reseller_id = next(
        (value for name, value in specs if name.lower() == "resellerid"), None
    )
    if reseller_id is not None:
        reseller_info["resellerId"] = reseller_id
    rslr_ind = next(
        (value for name, value in specs if name.lower() == "rslrctacemailind"),
        None,
    )
    reseller_emails = [
        value for name, value in specs if name.lower() == "resellerctacemail"
    ]
    # Rich mode without rslrCTACEmailInd routes resellerctacemail into
    # vmfAdditionalAttributes (not resellerInfo.email).
    reseller_email: str | None = None
    if sap or not rich:
        reseller_email = _reseller_email(specs)
    elif rslr_ind is not None:
        reseller_email = reseller_emails[0] if reseller_emails else rslr_ind
    if reseller_email is not None:
        reseller_info["email"] = reseller_email
        if not rich and not sap:
            reseller_info["companyName"] = _company_name_from_email(reseller_email)
    if reseller_info:
        body["resellerInfo"] = reseller_info

    if rich or sap:
        ship_to: dict[str, str] = {}
        ship_suffix = _clean_str(details.get("shiptosuffix"))
        if ship_suffix:
            ship_to["addressId"] = ship_suffix
        ship_address = details.get("shiptoaddress")
        if isinstance(ship_address, dict):
            contact = _clean_str(ship_address.get("attention")) or _clean_str(
                ship_address.get("name1")
            )
            if contact:
                ship_to["contact"] = contact
        if ship_to:
            body["shipToInfo"] = ship_to

    if rich:
        end_user: dict[str, str] = {}
        for name, value in specs:
            if name.lower() != "commenttext":
                continue
            parsed = _split_eu_comment(value)
            if parsed is None:
                continue
            key, text = parsed
            field = EU_COMMENT_FIELD_MAP.get(key)
            if field is not None:
                end_user[field] = text
        if end_user:
            if "name1" in end_user:
                end_user.setdefault("contact", end_user["name1"])
            body["endUserInfo"] = end_user

    credit_card = _convert_credit_card(details)
    if credit_card is not None:
        body["creditCardDetails"] = credit_card

    if rich:
        vmf = _convert_vmf(details)
        if vmf is not None:
            body["vmf"] = vmf

        vmf_additional: list[dict[str, str]] = []
        reseller_email_seen = 0
        has_quote_vmf = "quoteNumber" in body or "vmf" in body
        for name, value in specs:
            lower = name.lower()
            if lower in HEADER_SPECS_TO_VMF:
                # eushipctacnam only appears on quote/VMF orders.
                if lower == "eushipctacnam" and not has_quote_vmf:
                    continue
                vmf_additional.append(
                    {
                        "attributeName": HEADER_SPECS_TO_VMF[lower],
                        "attributeValue": value,
                    }
                )
            elif lower == "resellerctacemail":
                reseller_email_seen += 1
                # All resellerctacemail values go to vmfAdditionalAttributes
                # when there is no rslrCTACEmailInd; otherwise only duplicates.
                if rslr_ind is None or reseller_email_seen > 1:
                    vmf_additional.append(
                        {"attributeName": name, "attributeValue": value}
                    )
        if vmf_additional:
            body["vmfAdditionalAttributes"] = vmf_additional

    body["lines"] = _convert_lines(
        details,
        rich=rich,
        sap=sap,
        has_basket=(
            any(name.lower() == "basketid" for name, _ in specs)
            and "quoteNumber" not in body
            and not any(
                name.lower() in {"quoteid", "quotenumber", "quoteguid"}
                for name, _ in specs
            )
            and _convert_vmf(details) is None
        ),
    )

    if rich:
        signature = next(
            (
                value
                for name, value in specs
                if name.lower() == "signaturerequired"
            ),
            None,
        )
        if signature is not None:
            body["shipmentDetails"] = {"signatureRequired": _to_bool(signature)}

    if sap:
        attributes = _build_sap_additional_attributes(specs, allow_partial)
        body["additionalAttributes"] = attributes
    elif rich:
        attributes = [
            {"attributeName": "delinotifemail", "attributeValue": ""},
            {"attributeName": "smsnumber", "attributeValue": ""},
        ]
        if allow_partial is not None:
            attributes.append(
                {
                    "attributeName": "allowPartialOrder",
                    "attributeValue": allow_partial,
                }
            )
        duplicate = next(
            (
                value
                for name, value in specs
                if name.lower() == "duplicatecustomerordernumbervalidate"
            ),
            None,
        )
        if duplicate is not None:
            attributes.append(
                {
                    "attributeName": "allowDuplicateCustomerOrderNumber",
                    "attributeValue": (
                        "true" if duplicate.upper() == "ALLOW" else "false"
                    ),
                }
            )
        for name, value in specs:
            lower = name.lower()
            if lower in HEADER_SPECS_DROPPED or lower.startswith("im-"):
                continue
            if lower in HEADER_SPECS_CONSUMED or lower in HEADER_SPECS_TO_VMF:
                continue
            if lower == "resellerctacemail" or name == "quoteNumber":
                continue
            if lower == "commenttext" and _split_eu_comment(value) is not None:
                continue
            attributes.append({"attributeName": name, "attributeValue": value})
        body["additionalAttributes"] = attributes
    else:
        attributes = [
            {"attributeName": "enableCommentsAsLines", "attributeValue": "true"},
        ]
        duplicate = next(
            (
                value
                for name, value in specs
                if name.lower() == "duplicatecustomerordernumbervalidate"
            ),
            None,
        )
        if duplicate is not None:
            attributes.append(
                {
                    "attributeName": "allowDuplicateCustomerOrderNumber",
                    "attributeValue": (
                        "true" if duplicate.upper() == "ALLOW" else "false"
                    ),
                }
            )
        attributes.append(
            {
                "attributeName": "allowOrderOnCustomerHold",
                "attributeValue": "false",
            }
        )
        entrymethod = _entrymethod(specs)
        allow = set(SIMPLE_ATTR_ALLOWLIST)
        # WEBS portal samples omit these; ACTO/XWEB/others keep them.
        if entrymethod and entrymethod != "WEBS":
            allow |= SIMPLE_ATTR_XWEB_ALLOWLIST
        for name, value in specs:
            if name.lower() in allow:
                attributes.append(
                    {"attributeName": name, "attributeValue": value}
                )
        body["additionalAttributes"] = attributes

    return body


# SAP header attribute renames / drops.
SAP_ATTR_RENAME: dict[str, str] = {
    "ordertype": "orderType",
    "reasoncode": "channelCode",
}
SAP_ATTR_DROPPED: frozenset[str] = frozenset(
    {
        "shipmentcompleteflag",
        "resellerctacemail",
        "rslrctacemailind",
        "callingapplication",
        "signaturerequired",
        "isgdsapiinvoked",
        "orderdoctype",
        "isasync",
        "isdirectshiporder",
        "resellerid",
    }
)


def _build_sap_additional_attributes(
    specs: list[tuple[str, str]],
    allow_partial: str | None,
) -> list[dict[str, str]]:
    attributes: list[dict[str, str]] = []
    # Force continueonerror=N / allowPartialOrder=true for SAP returns.
    emitted_continue = False
    emitted_partial = False
    emitted_duplicate = False

    for name, value in specs:
        lower = name.lower()
        if lower in SAP_ATTR_DROPPED or lower.startswith("im-"):
            continue
        if lower == "continueonerror":
            attributes.append(
                {"attributeName": "continueonerror", "attributeValue": "N"}
            )
            emitted_continue = True
            continue
        if lower == "duplicatecustomerordernumbervalidate":
            attributes.append(
                {
                    "attributeName": "allowDuplicateCustomerOrderNumber",
                    "attributeValue": (
                        "true" if value.upper() == "ALLOW" else "false"
                    ),
                }
            )
            emitted_duplicate = True
            continue
        attr_name = SAP_ATTR_RENAME.get(lower, name)
        attributes.append({"attributeName": attr_name, "attributeValue": value})

    if not emitted_continue:
        attributes.append(
            {"attributeName": "continueonerror", "attributeValue": "N"}
        )
    if allow_partial is not None:
        # Insert near continueonerror if not already present from a rename.
        if not any(a["attributeName"] == "allowPartialOrder" for a in attributes):
            attributes.append(
                {
                    "attributeName": "allowPartialOrder",
                    "attributeValue": allow_partial,
                }
            )
            emitted_partial = True
    if not emitted_duplicate:
        attributes.append(
            {
                "attributeName": "allowDuplicateCustomerOrderNumber",
                "attributeValue": "true",
            }
        )
    _ = emitted_partial  # reserved for future ordering tweaks
    return attributes
