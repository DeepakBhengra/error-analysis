import {
  BarChart,
  Callout,
  Card,
  CardBody,
  CardHeader,
  Code,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  Pill,
  Row,
  Stack,
  Stat,
  Table,
  Text,
} from "cursor/canvas";

const DIFF_ROWS = [
  {
    signal: "lines[].directShipConfigAttributes",
    d: "78%",
    s: "33%",
    note: "Strongest D marker",
  },
  {
    signal: "lines[].lineType present",
    d: "78%",
    s: "33%",
    note: "Usually P on D lines",
  },
  {
    signal: "costoverrideflag=true",
    d: "44%",
    s: "0%",
    note: "D-only in sample",
  },
  {
    signal: "header vmf[]",
    d: "78%",
    s: "44%",
    note: "Vendor fulfillment path",
  },
  {
    signal: "isDirectShipOrder=true",
    d: "~44%",
    s: "0%",
    note: "S uses false when set",
  },
  {
    signal: "shipToInfo.addressLine1 filled",
    d: "67%",
    s: "100%",
    note: "S more complete ship-to",
  },
];

const MANDATORY_ROWS = [
  { field: "customerOrderNumber", scope: "header", rate: "100%" },
  { field: "resellerInfo.resellerId", scope: "header", rate: "100%" },
  { field: "resellerInfo.countryCode", scope: "header", rate: "100%" },
  { field: "lines[] (non-empty)", scope: "header", rate: "100%" },
  { field: "additionalAttributes", scope: "header", rate: "100%" },
  {
    field: "additionalAttributes[allowDuplicateCustomerOrderNumber]",
    scope: "header",
    rate: "100%",
  },
  {
    field: "additionalAttributes[ordertotalvalue]",
    scope: "header",
    rate: "100%",
  },
  { field: "shipmentDetails.signatureRequired", scope: "header", rate: "100%" },
  { field: "vmfAdditionalAttributes", scope: "header", rate: "100%" },
  { field: "endCustomerOrderNumber", scope: "header", rate: "89%" },
  { field: "lines[].customerLineNumber", scope: "line", rate: "100%" },
  { field: "lines[].quantity", scope: "line", rate: "100%" },
  { field: "lines[].vendorPartNumber", scope: "line", rate: "100%" },
  { field: "lines[].globalSkuId", scope: "line", rate: "100%" },
  { field: "lines[].unitPrice", scope: "line", rate: "100%" },
  { field: "lines[].endUserPrice", scope: "line", rate: "100%" },
  { field: "lines[].specialPrice", scope: "line", rate: "100%" },
  { field: "lines[].aucSelectionCost", scope: "line", rate: "100%" },
  { field: "lines[].additionalAttributes", scope: "line", rate: "100%" },
];

const D_SPECIFIC = [
  {
    field: "lines[].directShipConfigAttributes",
    detail:
      "vendornumber, stdcostamount, discountedcost, discountedprice, zerodollarflag",
  },
  {
    field: 'additionalAttributes[isDirectShipOrder] = "true"',
    detail: "Set by some client paths; never true on S samples",
  },
  {
    field: 'lines[].additionalAttributes[costoverrideflag] = "true"',
    detail: "Seen only on D in this set (vendor deals / special cost)",
  },
  {
    field: "header vmf[]",
    detail:
      "vendorNumber (+ quoteNumber / vendAuthNumber) — alternate D path without DSC",
  },
];

const D_ORDERS = [
  "2571",
  "PO113046",
  "CNB6072412",
  "1514228",
  "OC-Y26-393",
  "BEST29.07.MAIL",
  "PO-0448",
  "TESTIFBID01",
  "167439",
];

const S_ORDERS = [
  "SERVIAP",
  "176902-0",
  "4500779705",
  "P27901559",
  "24470",
  "4519549977",
  "PO8035607-INT",
  "4700088087",
  "M75Q+E14",
];

export default function OrderTypeDsCompare() {
  return (
    <Stack gap={20}>
      <Stack gap={6}>
        <H1>D vs S Order Create v6</H1>
        <Text tone="secondary">
          Production SUCCESS inbound requests · Datadog hosts uschileai1401–1404
          · ~30 days ending 2026-07-29 · 9 pure-D vs 9 pure-S (mixed PO
          PONUK2017101 excluded)
        </Text>
      </Stack>

      <Callout tone="warning" title="orderType is a response field">
        Response orders[].orderType is D (direct ship) or S (stock). Inbound
        requests almost never send a meaningful additionalAttributes[orderType]
        — it is missing or empty. D vs S is assigned from product / fulfillment
        path, not by declaring orderType on the request.
      </Callout>

      <Grid columns={4} gap={12}>
        <Stat value="9" label="Pure D samples" />
        <Stat value="9" label="Pure S samples" />
        <Stat value="78%" label="D with directShipConfig" tone="success" />
        <Stat value="0%" label="S with costoverride=true" tone="info" />
      </Grid>

      <H2>Significant differences</H2>
      <Text tone="secondary">
        Field presence rates on inbound v6 bodies that produced SUCCESS
        responses with the given orderType.
      </Text>
      <BarChart
        title="D vs S field presence"
        categories={[
          "directShipConfig",
          "lineType",
          "costoverride",
          "vmf",
          "shipTo addr",
        ]}
        series={[
          {
            name: "D rate %",
            data: [78, 78, 44, 78, 67],
            tone: "accent",
          },
          {
            name: "S rate %",
            data: [33, 33, 0, 44, 100],
            tone: "neutral",
          },
        ]}
        height={220}
      />
      <Table
        columns={[
          { id: "signal", header: "Signal", flex: 1.6 },
          { id: "d", header: "D", width: 70, align: "right" },
          { id: "s", header: "S", width: 70, align: "right" },
          { id: "note", header: "Notes", flex: 1.2 },
        ]}
        rows={DIFF_ROWS.map((r) => ({
          signal: r.signal,
          d: r.d,
          s: r.s,
          note: r.note,
          tone:
            r.signal.includes("directShip") || r.signal.includes("costoverride")
              ? ("success" as const)
              : undefined,
        }))}
      />

      <H2>Mandatory on SUCCESS D (base v6 shape)</H2>
      <Text tone="secondary">
        Present on all (or ≥89%) D samples. Most are shared with S — base
        SUCCESS payload, not D-exclusive.
      </Text>
      <Table
        columns={[
          { id: "field", header: "Field", flex: 2 },
          { id: "scope", header: "Scope", width: 90 },
          { id: "rate", header: "D rate", width: 80, align: "right" },
        ]}
        rows={MANDATORY_ROWS.map((r) => ({
          field: r.field,
          scope: r.scope,
          rate: r.rate,
        }))}
      />

      <H2>D-specific / strongly recommended</H2>
      <Text tone="secondary">
        Not always exclusive, but these separate D from S in production and are
        the practical knobs to target a D outcome.
      </Text>
      <Stack gap={10}>
        {D_SPECIFIC.map((item) => (
          <Card key={item.field}>
            <CardHeader trailing={<Pill tone="success" size="sm">D</Pill>}>
              {item.field}
            </CardHeader>
            <CardBody>
              <Text>{item.detail}</Text>
            </CardBody>
          </Card>
        ))}
      </Stack>

      <H2>Sample customer order numbers</H2>
      <Grid columns={2} gap={12}>
        <Card>
          <CardHeader>D responses</CardHeader>
          <CardBody>
            <Row gap={6} wrap>
              {D_ORDERS.map((po) => (
                <Pill key={po} size="sm">
                  {po}
                </Pill>
              ))}
            </Row>
          </CardBody>
        </Card>
        <Card>
          <CardHeader>S responses</CardHeader>
          <CardBody>
            <Row gap={6} wrap>
              {S_ORDERS.map((po) => (
                <Pill key={po} size="sm">
                  {po}
                </Pill>
              ))}
            </Row>
          </CardBody>
        </Card>
      </Grid>

      <Divider />

      <H3>Bottom line</H3>
      <Stack gap={8}>
        <Text>
          1. Filter SUCCESS D/S on the response (`orders[].orderType`), then
          pull the inbound `lines[]` request for that PO.
        </Text>
        <Text>
          2. Base mandatory v6 fields are shared by D and S (PO, resellerId,
          lines with VPN/SKU/qty/prices, additionalAttributes,
          shipmentDetails).
        </Text>
        <Text>
          3. To produce D: include{" "}
          <Code>lines[].directShipConfigAttributes</Code> and/or{" "}
          <Code>isDirectShipOrder=true</Code> / header <Code>vmf</Code>.
        </Text>
      </Stack>

      <Text tone="secondary" size="small">
        Artifacts: results/order-type-ds-compare/ (d-samples.json,
        s-samples.json, REPORT.md)
      </Text>
    </Stack>
  );
}
