from __future__ import annotations

import json

import pytest

from error_analysis.order_create.v2_to_v6 import (
    OrderCreateV2ToV6Error,
    convert_v2_to_v6,
)

EMPTY_CREDIT_CARD_V2 = {
    "creditcardnumber": "",
    "paymentcode": "",
    "cardtype": "",
    "expirationdate": "",
    "cvvcheckbox": "",
    "securitycode": "",
    "firstname": "",
    "lastname": "",
    "authorizationprovider": "",
    "authorizationcode": "",
    "address": "",
    "city": "",
    "state": "",
    "postalcode": "",
    "paymentgroup": "",
    "paymentcardtype": "",
    "currency": "",
    "authdate": "",
    "authtime": "",
    "requestid": "",
}

EMPTY_CREDIT_CARD_V6 = {
    "cardNumber": "",
    "paymentCode": "",
    "cardType": "",
    "expirationDate": "",
    "securityCode": "",
    "firstName": "",
    "lastName": "",
    "authorizationCode": "",
    "address": "",
    "city": "",
    "state": "",
    "postalCode": "",
    "authorizationAmount": "",
}


def _sample_v2_request() -> dict:
    return {
        "ordercreaterequest": {
            "requestpreamble": {
                "isocountrycode": "US",
                "customernumber": "60-006843",
            },
            "ordercreatedetails": {
                "systemid": "A300",
                "customerponumber": "DEEPAKDDTEST21",
                "ompordernumber": "0220270872",
                "enduserordernumber": "DEEPAKDDTEST21",
                "shiptoaddress": {},
                "enduser": {},
                "creditcarddetails": dict(EMPTY_CREDIT_CARD_V2),
                "ssenduserinfo": {},
                "lines": [
                    {
                        "linetype": "P",
                        "linenumber": "002",
                        "globalskuid": "A300-9Y6772AA",
                        "quantity": 1.0,
                        "ingrampartnumber": "9Y6772AA",
                        "enduserponumber": "DEEPAKDDTEST21",
                        "netamount": 0.0,
                        "enduser": {"endusercontact": {}},
                        "vmf": {},
                        "variantconfiguration": {},
                        "productextendedspecs": [
                            {"attributename": "everestflag"},
                            {
                                "attributename": "IM-CORRELATIONID",
                                "attributevalue": "123-1",
                            },
                        ],
                        "vendorparams": {"pricelist": {}},
                    },
                    {
                        "linetype": "P",
                        "linenumber": "003",
                        "globalskuid": "A300-9Y7663AA",
                        "quantity": 1.0,
                        "ingrampartnumber": "9Y7663AA",
                        "enduserponumber": "DEEPAKDDTEST21",
                        "netamount": 0.0,
                        "enduser": {
                            "name1": "vanessa",
                            "phonenumber": "7145661000",
                            "email": "vanessa@ingram.com",
                            "endusercontact": {},
                        },
                        "vmf": {},
                        "variantconfiguration": {},
                        "productextendedspecs": [
                            {
                                "attributename": "enduseremail",
                                "attributevalue": "vanessa@ingram.com",
                            },
                            {
                                "attributename": "enduserphone",
                                "attributevalue": "7145661000",
                            },
                            {
                                "attributename": "IM-CORRELATIONID",
                                "attributevalue": "123-1",
                            },
                        ],
                        "serviceextendedspecs": [
                            {
                                "attributename": "MUUsage",
                                "attributevalue": "WA",
                            },
                        ],
                        "vendorparams": {"pricelist": {}},
                    },
                ],
                "extendedspecs": [
                    {
                        "attributename": "rslrCTACEmailInd",
                        "attributevalue": "this.Company@demo.com",
                    },
                    {"attributename": "entrymethod", "attributevalue": "WEBS"},
                    {
                        "attributename": "callingapplication",
                        "attributevalue": "apiportal",
                    },
                    {
                        "attributename": "signaturerequired",
                        "attributevalue": "N",
                    },
                    {
                        "attributename": "continueonerror",
                        "attributevalue": "Y",
                    },
                    {
                        "attributename": "duplicatecustomerordernumbervalidate",
                        "attributevalue": "ALLOW",
                    },
                    {
                        "attributename": "eudepid",
                        "attributevalue": "DepIDTest1",
                    },
                    {"attributename": "depordernbr", "attributevalue": "Test1"},
                    {
                        "attributename": "resellerctacemail",
                        "attributevalue": "this.Company@demo.com",
                    },
                    {
                        "attributename": "IM-CORRELATIONID",
                        "attributevalue": "123",
                    },
                    {"attributename": "IM-SENDERID", "attributevalue": "vanessa"},
                    {"attributename": "orderdoctype", "attributevalue": "WEBS"},
                    {
                        "attributename": "isgdsapiinvoked",
                        "attributevalue": "true",
                    },
                ],
                "vendorparams": {"pricelist": {}},
                "entityinfo": [{}],
            },
        }
    }


FR_SAMPLE_V2 = r"""
{"ordercreaterequest":{"requestpreamble":{"isocountrycode":"FR","customernumber":"20-222222"},"ordercreatedetails":{"systemid":"A304","customerponumber":"COMBD17JUL027","ompordernumber":"0220270866","billtosuffix":"000","shiptosuffix":"200","shiptoaddress":{"attention":"PRASAD PHODKAR","name1":"PRASAD PHODKAR"},"enduser":{},"creditcarddetails":{"creditcardnumber":"","paymentcode":"","cardtype":"","expirationdate":"","cvvcheckbox":"","securitycode":"","firstname":"","lastname":"","authorizationprovider":"","authorizationcode":"","address":"","city":"","state":"","postalcode":"","paymentgroup":"","paymentcardtype":"","currency":"","authdate":"","authtime":"","requestid":""},"vmf":{"quotenumber":"QN333","vendauthnumber":"ANJ22","csnumber":"CS3499","vendornumber":"Y988","veud":{},"vmfspecs":[{"attributename":"commenttext","attributevalue":"HEADER"},{"attributename":"lineextracommenttext","attributevalue":"H:CS3499"}]},"ssenduserinfo":{},"lines":[{"linetype":"P","linenumber":"001","globalskuid":"A300-6GT250","quantity":1.0,"ingrampartnumber":"6GT250","vendorpartnumber":"FC-10-90AP1-639-02-12","enduserponumber":"DUMMY","enduserprice":0.0,"warehouseid":"10","carriercode":"VL","unitprice":102.07,"acoptrackingnumber":"022238610","netamount":0.0,"enduser":{"endusercontact":{}},"vmf":{},"variantconfiguration":{},"productextendedspecs":[{"attributename":"aucselectioncost","attributevalue":"0.0"},{"attributename":"gsaflag","attributevalue":"Y"},{"attributename":"authbidnumber","attributevalue":"US_AQCOMB_RSLREU"},{"attributename":"enduserid","attributevalue":"86198"},{"attributename":"addresssequencenumber","attributevalue":"1"},{"attributename":"contactid","attributevalue":"1"},{"attributename":"enduseracopid","attributevalue":"7186793"},{"attributename":"commenttext","attributevalue":"H:BN7882"},{"attributename":"quoteproductguid","attributevalue":"b76e3db2-c181-f111-ab0f-7ced8d6f6772"},{"attributename":"pricefactid","attributevalue":"c98a5258-d813-40e6-ba45-4cf16c744df0"},{"attributename":"isheadervmfmissing","attributevalue":"false"},{"attributename":"islinevmfmissing","attributevalue":"false"},{"attributename":"prodmdlnumber","attributevalue":"MN5663"},{"attributename":"unitpriceswitch","attributevalue":"Y"},{"attributename":"IM-CORRELATIONID","attributevalue":"e348dd87-5125-ee11-9cbd-002248280c14-1"}],"vendorparams":{"pricelist":{}}}],"extendedspecs":[{"attributename":"isAsync","attributevalue":"True"},{"attributename":"rslrCTACEmailInd","attributevalue":"prasad.phodkar@ingrammicro.com"},{"attributename":"callingapplication","attributevalue":"apiportal"},{"attributename":"commenttext","attributevalue":"EUNAME: TESTEU AQCOMBINE"},{"attributename":"commenttext","attributevalue":"EUNAME1: TEST AQCOMB"},{"attributename":"commenttext","attributevalue":"EUADD1: TESTING AQCOMBINE US"},{"attributename":"commenttext","attributevalue":"EUPH: 1289012890"},{"attributename":"commenttext","attributevalue":"EUEMAIL: TESTAQCOMB@TEST.COM"},{"attributename":"signaturerequired","attributevalue":"N"},{"attributename":"duplicatecustomerordernumbervalidate","attributevalue":"ALLOW"},{"attributename":"continueonerror","attributevalue":"N"},{"attributename":"basketid","attributevalue":"7df8fafa-e1fa-40fb-a050-08373e8c0fae"},{"attributename":"userid","attributevalue":"18f39dd6-c996-4d42-b5c5-449a316fc8a1"},{"attributename":"salesorganization","attributevalue":"SALE00"},{"attributename":"distributionchannel","attributevalue":"10"},{"attributename":"division","attributevalue":"MD"},{"attributename":"ordertotalvalue","attributevalue":"102.07"},{"attributename":"regioncode","attributevalue":"MD"},{"attributename":"commenttext","attributevalue":"BN-Order Comments"},{"attributename":"vlink","attributevalue":"True"},{"attributename":"entrymethod","attributevalue":"XQ2O"},{"attributename":"quoteid","attributevalue":"QUO-1384915-H5L7K9"},{"attributename":"quotenumber","attributevalue":"QUO-1384915-H5L7K9"},{"attributename":"quoteguid","attributevalue":"336edf78-c181-f111-ab0f-000d3a31984c"},{"attributename":"operatorid","attributevalue":"HERM"},{"attributename":"capsbuyerid","attributevalue":"SALE00"},{"attributename":"resellerid","attributevalue":"20222222"},{"attributename":"quoteNumber","attributevalue":"QUO-1384915-H5L7K9"},{"attributename":"resellerctacemail","attributevalue":"prasad.phodkar@ingrammicro.com"},{"attributename":"shipctacphone","attributevalue":"9892995368"},{"attributename":"eushipctacnam","attributevalue":"PRASAD PHODKAR"},{"attributename":"shipctacemail","attributevalue":"PRASADRULZ@GMAIL.COM"},{"attributename":"contractnumber","attributevalue":"CI8733"},{"attributename":"resellerctacemail","attributevalue":"PRASAD.PHODKAR@INGRAMMICRO.COM"},{"attributename":"IM-CORRELATIONID","attributevalue":"e348dd87-5125-ee11-9cbd-002248280c14"},{"attributename":"IM-SENDERID","attributevalue":"IMX4A"},{"attributename":"IM-Callbackurl","attributevalue":"https://ee7571af9f5155bb9fec81c009a1ecc4.m.pipedream.net"},{"attributename":"IM-CallbackAuthorizationHeader","attributevalue":"Basic QVBQSU0zNjA6QVBQSU0zNjAxMjM0"},{"attributename":"IM-Environment","attributevalue":"stage2"},{"attributename":"IM-SiteCode","attributevalue":"US"},{"attributename":"isdirectshiporder","attributevalue":"true"}],"vendorparams":{"pricelist":{}},"entityinfo":[{}]}}}
"""


def _fr_v2_request() -> dict:
    return json.loads(FR_SAMPLE_V2)


def test_convert_sample_v2_to_v6() -> None:
    body = convert_v2_to_v6(_sample_v2_request())

    assert body["customerOrderNumber"] == "DEEPAKDDTEST21"
    assert body["endCustomerOrderNumber"] == "DEEPAKDDTEST21"
    assert body["billToAddressId"] == ""
    assert "allowPartialOrder" not in body  # continueonerror=Y
    assert "notes" not in body
    assert body["resellerInfo"] == {
        "companyName": "Demo",
        "email": "this.Company@demo.com",
    }
    assert "shipToInfo" not in body
    assert "endUserInfo" not in body
    assert body["creditCardDetails"] == EMPTY_CREDIT_CARD_V6
    assert "vmf" not in body
    assert "vmfAdditionalAttributes" not in body
    assert "shipmentDetails" not in body
    assert body["lines"] == [
        {
            "customerLineNumber": "002",
            "ingramPartNumber": "9Y6772AA",
            "quantity": 1,
        },
        {
            "customerLineNumber": "003",
            "ingramPartNumber": "9Y7663AA",
            "quantity": 1,
            "endUserInfo": [
                {
                    "contact": "vanessa",
                    "phoneNumber": 7145661000,
                    "email": "vanessa@ingram.com",
                }
            ],
        },
    ]
    assert body["additionalAttributes"] == [
        {"attributeName": "enableCommentsAsLines", "attributeValue": "true"},
        {
            "attributeName": "allowDuplicateCustomerOrderNumber",
            "attributeValue": "true",
        },
        {"attributeName": "allowOrderOnCustomerHold", "attributeValue": "false"},
        {"attributeName": "eudepid", "attributeValue": "DepIDTest1"},
        {"attributeName": "depordernbr", "attributeValue": "Test1"},
    ]


def test_convert_fr_sample_top_level() -> None:
    body = convert_v2_to_v6(_fr_v2_request())

    assert body["customerOrderNumber"] == "COMBD17JUL027"
    assert "endCustomerOrderNumber" not in body  # no enduserordernumber in v2
    assert body["billToAddressId"] == "000"
    assert body["allowPartialOrder"] == "false"  # continueonerror=N
    assert body["quoteNumber"] == "QUO-1384915-H5L7K9"
    assert body["resellerInfo"] == {
        "resellerId": "20222222",
        "email": "prasad.phodkar@ingrammicro.com",
    }
    assert body["shipToInfo"] == {
        "addressId": "200",
        "contact": "PRASAD PHODKAR",
    }
    assert body["endUserInfo"] == {
        "companyName": "TESTEU AQCOMBINE",
        "name1": "TEST AQCOMB",
        "contact": "TEST AQCOMB",
        "addressLine1": "TESTING AQCOMBINE US",
        "phoneNumber": "1289012890",
        "email": "TESTAQCOMB@TEST.COM",
    }
    assert body["creditCardDetails"] == EMPTY_CREDIT_CARD_V6
    assert body["shipmentDetails"] == {"signatureRequired": False}


def test_convert_fr_sample_vmf() -> None:
    body = convert_v2_to_v6(_fr_v2_request())

    assert body["vmf"] == [
        {
            "quoteNumber": "QN333",
            "vendAuthNumber": "ANJ22",
            "csnNumber": "CS3499",
            "vendorNumber": "Y988",
            "vmfspecs": [
                {"attributeName": "commenttext", "attributeValue": "HEADER"},
                {
                    "attributeName": "lineextracommenttext",
                    "attributeValue": "H:CS3499",
                },
            ],
        }
    ]
    assert body["vmfAdditionalAttributes"] == [
        {"attributeName": "shipctacphone", "attributeValue": "9892995368"},
        {"attributeName": "eushipctacnam", "attributeValue": "PRASAD PHODKAR"},
        {
            "attributeName": "shipctacemail",
            "attributeValue": "PRASADRULZ@GMAIL.COM",
        },
        {"attributeName": "contractNumber", "attributeValue": "CI8733"},
        {
            "attributeName": "resellerctacemail",
            "attributeValue": "PRASAD.PHODKAR@INGRAMMICRO.COM",
        },
    ]


def test_convert_fr_sample_line() -> None:
    body = convert_v2_to_v6(_fr_v2_request())

    assert len(body["lines"]) == 1
    line = body["lines"][0]
    assert line["customerLineNumber"] == "001"
    assert line["globalSkuId"] == "A300-6GT250"
    assert "ingramPartNumber" not in line
    assert line["vendorPartNumber"] == "FC-10-90AP1-639-02-12"
    assert line["quantity"] == 1
    assert line["unitPrice"] == 102.07
    assert line["specialPrice"] == "0"
    assert line["endUserPoNumber"] == "DUMMY"
    assert line["endUserPrice"] == 0.0
    assert line["carrierCode"] == "VL"
    assert line["aucSelectionCost"] == 0.0
    assert line["acopTrackingNumber"] == "022238610"
    assert line["endUserInfo"] == [{}]
    assert line["vmfAdditionalAttributes"] == [
        {"attributeName": "prodmdlnumber", "attributeValue": "MN5663"},
    ]
    assert line["additionalAttributes"] == [
        {"attributeName": "shipFromWareHouseId", "attributeValue": "10"},
        {"attributeName": "gsaflag", "attributeValue": "Y"},
        {"attributeName": "authBidNumber", "attributeValue": "US_AQCOMB_RSLREU"},
        {"attributeName": "enduserid", "attributeValue": "86198"},
        {"attributeName": "addresssequencenumber", "attributeValue": "1"},
        {"attributeName": "contactid", "attributeValue": "1"},
        {"attributeName": "enduseracopid", "attributeValue": "7186793"},
        {"attributeName": "commenttext", "attributeValue": "H:BN7882"},
        {
            "attributeName": "quoteproductguid",
            "attributeValue": "b76e3db2-c181-f111-ab0f-7ced8d6f6772",
        },
        {
            "attributeName": "pricefactid",
            "attributeValue": "c98a5258-d813-40e6-ba45-4cf16c744df0",
        },
        {"attributeName": "isHeaderVMFMissing", "attributeValue": "false"},
        {"attributeName": "isLineVMFMissing", "attributeValue": "false"},
    ]


def test_convert_fr_sample_additional_attributes() -> None:
    body = convert_v2_to_v6(_fr_v2_request())

    assert body["additionalAttributes"] == [
        {"attributeName": "delinotifemail", "attributeValue": ""},
        {"attributeName": "smsnumber", "attributeValue": ""},
        {"attributeName": "allowPartialOrder", "attributeValue": "false"},
        {
            "attributeName": "allowDuplicateCustomerOrderNumber",
            "attributeValue": "true",
        },
        {"attributeName": "continueonerror", "attributeValue": "N"},
        {
            "attributeName": "basketid",
            "attributeValue": "7df8fafa-e1fa-40fb-a050-08373e8c0fae",
        },
        {
            "attributeName": "userid",
            "attributeValue": "18f39dd6-c996-4d42-b5c5-449a316fc8a1",
        },
        {"attributeName": "salesorganization", "attributeValue": "SALE00"},
        {"attributeName": "distributionchannel", "attributeValue": "10"},
        {"attributeName": "division", "attributeValue": "MD"},
        {"attributeName": "ordertotalvalue", "attributeValue": "102.07"},
        {"attributeName": "regioncode", "attributeValue": "MD"},
        {"attributeName": "commenttext", "attributeValue": "BN-Order Comments"},
        {"attributeName": "vlink", "attributeValue": "True"},
        {"attributeName": "entrymethod", "attributeValue": "XQ2O"},
        {"attributeName": "quoteid", "attributeValue": "QUO-1384915-H5L7K9"},
        {
            "attributeName": "quotenumber",
            "attributeValue": "QUO-1384915-H5L7K9",
        },
        {
            "attributeName": "quoteguid",
            "attributeValue": "336edf78-c181-f111-ab0f-000d3a31984c",
        },
        {"attributeName": "operatorid", "attributeValue": "HERM"},
        {"attributeName": "capsbuyerid", "attributeValue": "SALE00"},
    ]


def test_convert_accepts_ordercreatedetails_directly() -> None:
    details = _sample_v2_request()["ordercreaterequest"]["ordercreatedetails"]
    body = convert_v2_to_v6(details)
    assert body["customerOrderNumber"] == "DEEPAKDDTEST21"


def test_notes_and_bill_to_overrides() -> None:
    body = convert_v2_to_v6(
        _sample_v2_request(),
        notes="Testing multiple Line items HW and WARR links",
        bill_to_address_id="ABC123",
    )
    assert body["notes"] == "Testing multiple Line items HW and WARR links"
    assert body["billToAddressId"] == "ABC123"


def test_duplicate_validate_not_allow_maps_false() -> None:
    request = _sample_v2_request()
    specs = request["ordercreaterequest"]["ordercreatedetails"]["extendedspecs"]
    for spec in specs:
        if spec["attributename"] == "duplicatecustomerordernumbervalidate":
            spec["attributevalue"] = "REJECT"
    body = convert_v2_to_v6(request)
    assert {
        "attributeName": "allowDuplicateCustomerOrderNumber",
        "attributeValue": "false",
    } in body["additionalAttributes"]


def test_non_product_lines_are_skipped() -> None:
    request = _sample_v2_request()
    request["ordercreaterequest"]["ordercreatedetails"]["lines"].append(
        {"linetype": "C", "linenumber": "004", "quantity": 1.0}
    )
    body = convert_v2_to_v6(request)
    assert [line["customerLineNumber"] for line in body["lines"]] == [
        "002",
        "003",
    ]


def test_missing_customerponumber_raises() -> None:
    with pytest.raises(OrderCreateV2ToV6Error):
        convert_v2_to_v6({"ordercreaterequest": {"ordercreatedetails": {}}})
    with pytest.raises(OrderCreateV2ToV6Error):
        convert_v2_to_v6(
            {
                "ordercreaterequest": {
                    "ordercreatedetails": {"customerponumber": "   "}
                }
            }
        )
