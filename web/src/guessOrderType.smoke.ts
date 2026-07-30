/**
 * Lightweight sanity checks for guessOrderType (run with: npx tsx or vite-node if available).
 * Kept as a module-side documentation example; primary validation is manual via CurlEditor.
 */
import { guessOrderTypeFromBody } from './guessOrderType'

function assert(cond: boolean, msg: string) {
  if (!cond) throw new Error(msg)
}

const dBody = {
  customerOrderNumber: 'PO-D',
  endCustomerOrderNumber: 'EU1',
  resellerInfo: { resellerId: '1', countryCode: 'US' },
  vmf: [{ vendorNumber: '564Z' }],
  additionalAttributes: [
    { attributeName: 'isDirectShipOrder', attributeValue: 'true' },
    { attributeName: 'carriercodeds', attributeValue: 'FX' },
    { attributeName: 'entryMethod', attributeValue: 'XWEB' },
    { attributeName: 'operatorId', attributeValue: 'HERM' },
    { attributeName: 'regionCode', attributeValue: 'US' },
  ],
  lines: [
    {
      customerLineNumber: '001',
      vendorPartNumber: 'VPN',
      quantity: 1,
      specialBidNumber: 'BID1',
      additionalAttributes: [
        { attributeName: 'contractStartDate', attributeValue: '2026-01-01' },
        { attributeName: 'contractEndDate', attributeValue: '2027-01-01' },
        { attributeName: 'costoverrideflag', attributeValue: 'true' },
      ],
      directShipConfigAttributes: [
        { attributeName: 'vendornumber', attributeValue: '564Z' },
        { attributeName: 'stdcostamount', attributeValue: '10' },
        { attributeName: 'discountedcost', attributeValue: '0' },
        { attributeName: 'discountedprice', attributeValue: '0' },
      ],
    },
  ],
}

const sBody = {
  customerOrderNumber: 'PO-S',
  billToAddressId: '000',
  currencyCode: 'USD',
  resellerInfo: { resellerId: '1', countryCode: 'US' },
  additionalAttributes: [
    { attributeName: 'OrderMode', attributeValue: 'STANDARD' },
    { attributeName: 'entrymethod', attributeValue: 'WEBS' },
    { attributeName: 'operatorid', attributeValue: 'PORTAL' },
    { attributeName: 'continueonerror', attributeValue: 'N' },
    { attributeName: 'capsbuyerid', attributeValue: 'X' },
    { attributeName: 'basketid', attributeValue: 'b1' },
  ],
  lines: [
    {
      customerLineNumber: '001',
      vendorPartNumber: 'VPN',
      quantity: 1,
      carrierCode: 'FX',
      warrantyInfo: { type: 'STD' },
      additionalAttributes: [{ attributeName: 'gsaflag', attributeValue: 'Y' }],
    },
  ],
}

const d = guessOrderTypeFromBody(dBody)
const s = guessOrderTypeFromBody(sBody)
assert(d.guess === 'D', `expected D got ${d.guess} ${d.detail}`)
assert(s.guess === 'S', `expected S got ${s.guess} ${s.detail}`)
assert(d.dScore > d.sScore, 'D score should dominate')
assert(s.sScore > s.dScore, 'S score should dominate')
console.log('ok', { d: { guess: d.guess, dScore: d.dScore, sScore: d.sScore }, s: { guess: s.guess, dScore: s.dScore, sScore: s.sScore } })
