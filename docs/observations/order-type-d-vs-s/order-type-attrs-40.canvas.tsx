import {
  BarChart,
  Callout,
  Card,
  CardBody,
  CardHeader,
  Grid,
  H1,
  H2,
  H3,
  Pill,
  Stack,
  Stat,
  Table,
  Text,
} from "cursor/canvas";

export default function OrderTypeAttrs40() {
  return (
    <Stack gap={20}>
      <Stack gap={6}>
        <H1>D vs S V6 attributes (n=39 each)</H1>
        <Text tone="secondary">
          Prod SUCCESS inbound requests · uschileai1401–1404 · ~45 days ending
          2026-07-29 · pure response orderType only
        </Text>
      </Stack>

      <Grid columns={4} gap={12}>
        <Stat value="39" label="D samples" />
        <Stat value="39" label="S samples" />
        <Stat value="80%" label="D with DSC block" tone="success" />
        <Stat value="2" label="S-exclusive attrs" tone="info" />
      </Grid>

      <Callout tone="info" title="S has few exclusive fields">
        Stock (S) requests are mostly identified by portal-style attributes and
        the absence of direct-ship markers. Direct (D) requests carry a much
        richer exclusive/enriched attribute set.
      </Callout>

      <H2>Strongest separators</H2>
      <Text tone="secondary" size="small">
        Presence rate on inbound v6 body (%)
      </Text>
      <BarChart
        categories={[
          "directShipConfig",
          "isDirectShipOrder",
          "header vmf",
          "contract dates",
          "OrderMode",
          "billToAddressId",
        ]}
        series={[
          {
            name: "D %",
            data: [80, 77, 82, 64, 5, 28],
            tone: "info",
          },
          {
            name: "S %",
            data: [10, 10, 20, 5, 31, 92],
            tone: "neutral",
          },
        ]}
        valueSuffix="%"
        height={240}
      />

      <H2>D-type specific (≥25% D, ≤10% S)</H2>
      <Table
        headers={["Attribute", "D", "S", "Location"]}
        columnAlign={["left", "right", "right", "left"]}
        rows={[
          ["print", "62%", "5%", "header attrs"],
          ["endusername", "59%", "5%", "header attrs"],
          ["isSalesMan", "59%", "8%", "header attrs"],
          ["provcontact*", "46–49%", "5%", "header attrs"],
          ["carriercodeds", "33%", "3%", "header attrs"],
          ["contractStart/EndDate", "64%", "5%", "line attrs"],
          ["enduseremail/phone", "31%", "3%", "line attrs"],
          ["specialBidNumber", "36%", "8%", "line field"],
          ["prodmdlnumber", "38%", "5%", "line VMF"],
          ["authBidNumber", "33%", "3%", "line VMF"],
          ["newcontractflag", "26%", "0%", "line VMF"],
          ["zerodollarflag", "26%", "0%", "DSC"],
        ]}
        striped
      />

      <H2>D-enriched (best practical markers)</H2>
      <Table
        headers={["Attribute / block", "D", "S"]}
        columnAlign={["left", "right", "right"]}
        rowTone={[
          "success",
          "success",
          "success",
          "success",
          "success",
          "success",
        ]}
        rows={[
          ["directShipConfigAttributes", "80%", "10%"],
          ["isDirectShipOrder", "77%", "10%"],
          ["DSC vendornumber/stdcost/discounted*", "74%", "10%"],
          ["header vmf[]", "82%", "20%"],
          ["lines[].vmf / vendorParams", "74%", "10%"],
          ["applicabletorenewal / tcc / tcv", "74%", "10%"],
        ]}
        striped
      />

      <Grid columns={2} gap={16}>
        <Stack gap={10}>
          <H2>S-type specific</H2>
          <Table
            headers={["Attribute", "D", "S", "Where"]}
            columnAlign={["left", "right", "right", "left"]}
            rows={[
              ["OrderMode", "5%", "31%", "header attrs"],
              ["currencyCode", "3%", "26%", "top-level"],
            ]}
          />
        </Stack>
        <Stack gap={10}>
          <H2>S-enriched</H2>
          <Table
            headers={["Attribute", "D", "S"]}
            columnAlign={["left", "right", "right"]}
            rows={[
              ["entrymethod / operatorid / continueonerror", "26%", "90%"],
              ["gsaflag", "26%", "90%"],
              ["billToAddressId", "28%", "92%"],
              ["basketid", "23%", "64%"],
              ["carrierCode (line)", "10%", "44%"],
              ["warrantyInfo", "10%", "36%"],
            ]}
            striped
          />
        </Stack>
      </Grid>

      <H3>Checklist</H3>
      <Grid columns={2} gap={12}>
        <Card>
          <CardHeader trailing={<Pill tone="success" size="sm">D</Pill>}>
            Likely direct ship
          </CardHeader>
          <CardBody>
            <Stack gap={6}>
              <Text>lines[].directShipConfigAttributes</Text>
              <Text>isDirectShipOrder=true</Text>
              <Text>header vmf[]</Text>
              <Text>contractStart/EndDate · carriercodeds · specialBidNumber</Text>
            </Stack>
          </CardBody>
        </Card>
        <Card>
          <CardHeader trailing={<Pill tone="info" size="sm">S</Pill>}>
            Likely stock
          </CardHeader>
          <CardBody>
            <Stack gap={6}>
              <Text>OrderMode and/or currencyCode</Text>
              <Text>entrymethod / operatorid / basketid / gsaflag</Text>
              <Text>billToAddressId populated</Text>
              <Text>No DSC / isDirectShipOrder / rich VMF cost block</Text>
            </Stack>
          </CardBody>
        </Card>
      </Grid>

      <Text tone="secondary" size="small">
        Saved in-repo: docs/observations/order-type-d-vs-s/ · classifier:
        web/src/guessOrderType.ts
      </Text>
    </Stack>
  );
}
