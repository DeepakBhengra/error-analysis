/**
 * Guess whether an Order Create v6 curl body is likely D (direct ship) or S (stock).
 *
 * Heuristic learned from prod SUCCESS samples (n≈39 each), documented in:
 *   docs/observations/order-type-d-vs-s/
 */

export type OrderTypeGuess = 'D' | 'S' | 'mixed' | 'unknown'

export interface OrderTypeHint {
  guess: OrderTypeGuess
  label: string
  detail: string
  dScore: number
  sScore: number
  dSignals: string[]
  sSignals: string[]
}

function attrMap(attrs: unknown): Record<string, string> {
  const out: Record<string, string> = {}
  if (!Array.isArray(attrs)) return out
  for (const item of attrs) {
    if (!item || typeof item !== 'object') continue
    const row = item as Record<string, unknown>
    const name = String(row.attributeName ?? row.attributename ?? '').trim()
    if (!name) continue
    const value = row.attributeValue ?? row.attributevalue
    out[name] = value == null ? '' : String(value).trim()
  }
  return out
}

function lowerKeyMap(attrs: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(attrs).map(([k, v]) => [k.toLowerCase(), v]),
  )
}

function hasKey(lower: Record<string, string>, ...names: string[]): boolean {
  return names.some((name) => name in lower && String(lower[name] ?? '').trim() !== '')
}

function truthy(value: string): boolean {
  const v = value.trim().toLowerCase()
  return v === 'true' || v === 'y' || v === 'yes' || v === '1'
}

function falsy(value: string): boolean {
  const v = value.trim().toLowerCase()
  return v === 'false' || v === 'n' || v === 'no' || v === '0'
}

function extractCurlBody(curl: string): Record<string, unknown> | null {
  const text = curl.replace(/\r\n/g, '\n')
  const marker = "--data-raw '"
  const start = text.indexOf(marker)
  if (start < 0) return null
  const jsonStart = start + marker.length
  const end = text.lastIndexOf("'")
  if (end <= jsonStart) return null
  try {
    const parsed = JSON.parse(text.slice(jsonStart, end))
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null
  } catch {
    return null
  }
}

function responseOrderTypes(body: Record<string, unknown>): string[] {
  const orders = body.orders
  if (!Array.isArray(orders)) return []
  const types: string[] = []
  for (const order of orders) {
    if (!order || typeof order !== 'object') continue
    const ot = String((order as Record<string, unknown>).orderType ?? '')
      .trim()
      .toUpperCase()
    if (ot) types.push(ot)
  }
  return types
}

function hint(
  guess: OrderTypeGuess,
  label: string,
  detail: string,
  dScore = 0,
  sScore = 0,
  dSignals: string[] = [],
  sSignals: string[] = [],
): OrderTypeHint {
  return { guess, label, detail, dScore, sScore, dSignals, sSignals }
}

function formatDetail(dScore: number, sScore: number, dSignals: string[], sSignals: string[]): string {
  const parts: string[] = []
  if (dSignals.length) parts.push(`D[${dScore}]: ${dSignals.join(', ')}`)
  if (sSignals.length) parts.push(`S[${sScore}]: ${sSignals.join(', ')}`)
  return parts.join(' · ')
}

/**
 * Score inbound v6 request body for D vs S likelihood.
 *
 * See docs/observations/order-type-d-vs-s/D-S-ATTRIBUTE-NOTES.md
 */
export function guessOrderTypeFromBody(body: Record<string, unknown>): OrderTypeHint {
  const responseTypes = [...new Set(responseOrderTypes(body))]
  if (responseTypes.length === 1 && (responseTypes[0] === 'D' || responseTypes[0] === 'S')) {
    const t = responseTypes[0]
    return hint(
      t,
      t === 'D' ? 'Probably D (direct ship)' : 'Probably S (stock)',
      `Response-shaped body has orders[].orderType = "${t}".`,
      t === 'D' ? 10 : 0,
      t === 'S' ? 10 : 0,
      t === 'D' ? ['orders[].orderType=D'] : [],
      t === 'S' ? ['orders[].orderType=S'] : [],
    )
  }
  if (responseTypes.includes('D') && responseTypes.includes('S')) {
    return hint(
      'mixed',
      'Mixed D + S',
      'Response-shaped body contains both D and S orderType values.',
      5,
      5,
      ['orders[].orderType=D'],
      ['orders[].orderType=S'],
    )
  }

  const headerAttrs = attrMap(body.additionalAttributes)
  const headerLower = lowerKeyMap(headerAttrs)
  const explicit = (headerLower.ordertype || '').trim().toUpperCase()
  if (explicit === 'D' || explicit === 'S') {
    return hint(
      explicit,
      explicit === 'D' ? 'Probably D (direct ship)' : 'Probably S (stock)',
      `additionalAttributes.orderType = "${explicit}".`,
      explicit === 'D' ? 10 : 0,
      explicit === 'S' ? 10 : 0,
      explicit === 'D' ? ['additionalAttributes.orderType=D'] : [],
      explicit === 'S' ? ['additionalAttributes.orderType=S'] : [],
    )
  }

  const dSignals: string[] = []
  const sSignals: string[] = []
  let dScore = 0
  let sScore = 0
  const bumpD = (points: number, label: string) => {
    dScore += points
    dSignals.push(label)
  }
  const bumpS = (points: number, label: string) => {
    sScore += points
    sSignals.push(label)
  }

  // Header — D
  const isDirect = headerLower.isdirectshiporder || ''
  if (truthy(isDirect)) bumpD(4, 'isDirectShipOrder=true')
  else if (falsy(isDirect)) bumpS(2, 'isDirectShipOrder=false')

  if (hasKey(headerLower, 'carriercodeds')) bumpD(2, 'carriercodeds')
  if (hasKey(headerLower, 'print')) bumpD(1, 'print')
  if (hasKey(headerLower, 'endusername')) bumpD(1, 'endusername')
  if (hasKey(headerLower, 'issalesman')) bumpD(1, 'isSalesMan')
  if (hasKey(headerLower, 'provcontactemail', 'provcontactname', 'provcontactphone')) {
    bumpD(2, 'provcontact*')
  }
  if ('deliNotifEmail' in headerAttrs && String(headerAttrs.deliNotifEmail || '').trim()) {
    bumpD(1, 'deliNotifEmail')
  }
  if (hasKey(headerLower, 'campaign')) bumpD(1, 'campaign')
  if (hasKey(headerLower, 'resellerenduserid')) bumpD(2, 'resellerenduserid')
  if (hasKey(headerLower, 'ismigration')) bumpD(1, 'ismigration')

  const dPathCamel = [
    'entryMethod',
    'operatorId',
    'regionCode',
    'euPoNumber',
    'thirdPartyFreightAccountNumber',
    'orderdoctype',
    'ordersubtype',
    'orderrecordid',
    'headerholdstatusflag',
  ]
  const dPathCount = dPathCamel.filter(
    (k) => k in headerAttrs && String(headerAttrs[k] ?? '').trim() !== '',
  ).length
  if (dPathCount >= 3) bumpD(3, `D-path cluster (${dPathCount})`)
  else if (dPathCount >= 1) bumpD(1, `D-path attrs (${dPathCount})`)

  // Header — S
  if (hasKey(headerLower, 'ordermode')) bumpS(3, 'OrderMode')

  const portalLowerNames = new Set([
    'entrymethod',
    'operatorid',
    'continueonerror',
    'capsbuyerid',
    'basketid',
    'regioncode',
    'delinotifemail',
  ])
  let portalCount = 0
  for (const key of Object.keys(headerAttrs)) {
    if (portalLowerNames.has(key.toLowerCase()) && key === key.toLowerCase()) {
      portalCount += 1
    }
  }
  if (portalCount >= 3) bumpS(3, `portal path (${portalCount})`)
  else if (portalCount >= 1) bumpS(1, `portal attrs (${portalCount})`)

  // Top-level
  if (typeof body.currencyCode === 'string' && body.currencyCode.trim()) {
    bumpS(2, 'currencyCode')
  }
  if (typeof body.billToAddressId === 'string' && body.billToAddressId.trim()) {
    bumpS(1, 'billToAddressId')
  }
  if (
    (typeof body.acceptBackOrder === 'string' && body.acceptBackOrder.trim()) ||
    typeof body.acceptBackOrder === 'boolean'
  ) {
    bumpD(1, 'acceptBackOrder')
  }
  if (typeof body.endCustomerOrderNumber === 'string' && body.endCustomerOrderNumber.trim()) {
    bumpD(1, 'endCustomerOrderNumber')
  }
  if (Array.isArray(body.vmf) && body.vmf.length > 0) bumpD(3, 'header vmf[]')

  const vmfHeader = lowerKeyMap(attrMap(body.vmfAdditionalAttributes))
  if (hasKey(vmfHeader, 'shipctacemail', 'eushipctacnam')) bumpD(1, 'vmf ship contact')

  // Lines
  const lines = body.lines
  let hasDsc = false
  let hasDscCostCore = false
  let hasZeroDollar = false
  let hasCostOverride = false
  let hasContractDates = false
  let hasEndUserContact = false
  let hasSpecialBid = false
  let hasAcop = false
  let hasLineVmf = false
  let hasVendorParams = false
  let hasWarranty = false
  let hasCarrierCode = false
  let hasGsa = false
  let hasTccTcv = false
  let hasLineVmfD = false

  if (Array.isArray(lines)) {
    for (const line of lines) {
      if (!line || typeof line !== 'object') continue
      const row = line as Record<string, unknown>

      const dsc = row.directShipConfigAttributes
      if (Array.isArray(dsc) && dsc.length > 0) {
        hasDsc = true
        const dscLower = lowerKeyMap(attrMap(dsc))
        if (
          hasKey(dscLower, 'vendornumber') &&
          hasKey(dscLower, 'stdcostamount', 'discountedcost', 'discountedprice')
        ) {
          hasDscCostCore = true
        }
        if (hasKey(dscLower, 'zerodollarflag')) hasZeroDollar = true
      }

      if (row.specialBidNumber) hasSpecialBid = true
      if (row.acopTrackingNumber) hasAcop = true
      if (row.vmf && typeof row.vmf === 'object') hasLineVmf = true
      if (row.vendorParams && typeof row.vendorParams === 'object') hasVendorParams = true
      if (row.warrantyInfo) hasWarranty = true
      if (typeof row.carrierCode === 'string' && row.carrierCode.trim()) hasCarrierCode = true

      const lineAttrs = lowerKeyMap(attrMap(row.additionalAttributes))
      if (truthy(lineAttrs.costoverrideflag || '')) hasCostOverride = true
      if (lineAttrs.contractstartdate || lineAttrs.contractenddate) hasContractDates = true
      if (lineAttrs.enduseremail || lineAttrs.enduserphone) hasEndUserContact = true
      const gsa = lineAttrs.gsaflag || ''
      if (truthy(gsa) || gsa.toUpperCase() === 'Y') hasGsa = true
      if (lineAttrs.applicabletorenewal || lineAttrs.tcc || lineAttrs.tcv) hasTccTcv = true

      const lineVmfAttrs = lowerKeyMap(attrMap(row.vmfAdditionalAttributes))
      if (hasKey(lineVmfAttrs, 'prodmdlnumber', 'authbidnumber', 'newcontractflag')) {
        hasLineVmfD = true
      }
    }
  }

  if (hasDsc) bumpD(4, 'directShipConfigAttributes')
  if (hasDscCostCore) bumpD(2, 'DSC cost core')
  if (hasZeroDollar) bumpD(1, 'zerodollarflag')
  if (hasCostOverride) bumpD(2, 'costoverrideflag=true')
  if (hasContractDates) bumpD(3, 'contractStart/EndDate')
  if (hasEndUserContact) bumpD(1, 'line enduseremail/phone')
  if (hasSpecialBid) bumpD(2, 'specialBidNumber')
  if (hasAcop) bumpD(1, 'acopTrackingNumber')
  if (hasLineVmf) bumpD(2, 'lines[].vmf')
  if (hasVendorParams) bumpD(2, 'lines[].vendorParams')
  if (hasTccTcv) bumpD(2, 'tcc/tcv/applicabletorenewal')
  if (hasLineVmfD) bumpD(2, 'line VMF bid/model attrs')

  if (hasGsa) bumpS(2, 'gsaflag')
  if (hasCarrierCode) bumpS(1, 'lines[].carrierCode')
  if (hasWarranty) bumpS(1, 'lines[].warrantyInfo')

  const detail = formatDetail(dScore, sScore, dSignals, sSignals)

  if (!Array.isArray(lines) || lines.length === 0) {
    return hint(
      'unknown',
      'Order type unclear',
      'Could not parse a v6 lines[] body from this curl.',
      dScore,
      sScore,
      dSignals,
      sSignals,
    )
  }

  if (dScore >= sScore + 2 && dScore >= 3) {
    return hint('D', 'Probably D (direct ship)', detail, dScore, sScore, dSignals, sSignals)
  }
  if (sScore >= dScore + 2 && sScore >= 3) {
    return hint('S', 'Probably S (stock)', detail, dScore, sScore, dSignals, sSignals)
  }
  if (dScore > sScore && dScore >= 2) {
    return hint('D', 'Probably D (direct ship)', detail, dScore, sScore, dSignals, sSignals)
  }
  if (sScore > dScore && sScore >= 2) {
    return hint('S', 'Probably S (stock)', detail, dScore, sScore, dSignals, sSignals)
  }
  if (dScore === 0) {
    return hint(
      'S',
      'Probably S (stock)',
      detail || 'No direct-ship markers (DSC / isDirectShipOrder / vmf / contract dates).',
      dScore,
      sScore,
      dSignals,
      sSignals,
    )
  }
  return hint(
    'unknown',
    'Order type unclear',
    detail || `Ambiguous scores D=${dScore} S=${sScore}.`,
    dScore,
    sScore,
    dSignals,
    sSignals,
  )
}

export function guessOrderTypeFromCurl(curl: string): OrderTypeHint | null {
  if (!curl.trim()) return null
  const body = extractCurlBody(curl)
  if (!body) return null
  return guessOrderTypeFromBody(body)
}
