import ConfidenceTag, {
  type ConfidenceTagKind,
} from "@/components/ConfidenceTag";
import { EVIDENCE_TAG_GLOSS } from "@/components/EvidenceTagLegend";
import QualityTag from "@/components/QualityTag";
import { allLayerLicenceCredits } from "@/lib/layerLicenceCredits";
import { LEDGER_FIXTURE_CONSTRAINTS, LEDGER_FIXTURE_ROWS } from "@/lib/ledger";
import { QUALITY_TAGS, QUALITY_TAG_GLOSS } from "@/lib/qualityTag";

const MINTLIFY = {
  introduction:
    "https://github.com/LJMoffat81/scot-land/blob/main/docs/mintlify/introduction.mdx",
  mapLayers:
    "https://github.com/LJMoffat81/scot-land/blob/main/docs/mintlify/map-layer-guide.mdx",
  apiReference:
    "https://github.com/LJMoffat81/scot-land/blob/main/docs/mintlify/api-reference.mdx",
};

const CONFIDENCE: Array<{
  kind: ConfidenceTagKind;
  gloss: string;
}> = [
  { kind: "market", gloss: `${EVIDENCE_TAG_GLOSS.market}.` },
  { kind: "proxy", gloss: `${EVIDENCE_TAG_GLOSS.proxy}.` },
  { kind: "shadow", gloss: `${EVIDENCE_TAG_GLOSS.shadow}.` },
];

function ledgerPublicTag(tag: string): string {
  switch (tag) {
    case "market":
      return "Market";
    case "proxy":
      return "Proxy";
    case "shadow":
      return "Shadow";
    case "market_or_proxy":
      return "Market / Proxy";
    case "nested":
      return "of which";
    case "reported":
      return "outside";
    default:
      return tag;
  }
}

const LAYER_CREDITS = allLayerLicenceCredits();

const LOOKUP_URL =
  "https://statistics.gov.scot/data/data-zone-lookup-2022";
const LOOKUP_OGL =
  "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/";

export default function MethodologyContent() {
  return (
    <main className="methodology-page" data-testid="methodology-page">
      <p className="meta" style={{ marginBottom: "0.5rem" }}>
        <a href="/">Map</a>
        {" · "}
        <a href="/data">Data</a>
        {" · "}
        <a href="/mission">Mission</a>
        {" · "}
        <a href="/methodology" aria-current="page">
          Methodology
        </a>
        {" · "}
        <a href="/downloads">Downloads</a>
        {" · "}
        <a href="/open-api">Public API</a>
      </p>
      <h1>Methodology</h1>
      <p className="downloads-note" data-testid="experimental-not-official">
        Research estimate, not an official valuation or bill. Figures pending
        sign-off. For now, figures are published at Data Zone level only, not
        for individual parcels, plots or addresses. Open data only at launch;
        paid sources may be added later, each clearly tagged; paid data never
        republished.
      </p>
      <p>
        Purpose and who the site is for: <a href="/mission">Mission</a>. Raw
        datasets and licences: <a href="/data">Data</a>.
      </p>
      <p>
        <a href="#agr">What AGR is</a>
        {" · "}
        <a href="#rollup">Roll-up</a>
        {" · "}
        <a href="#tags">Three tags</a>
        {" · "}
        <a href="#rents">Rents and constraints</a>
        {" · "}
        <a href="#ledger">Ledger</a>
        {" · "}
        <a href="#sources">Sources</a>
        {" · "}
        <a href="#gaps">Gaps</a>
        {" · "}
        <a href="#validation">Validation</a>
        {" · "}
        <a href="#changelog">Changelog</a>
      </p>

      <section id="agr">
        <h2>What AGR is</h2>
        <p>
          <strong>Annual Ground Rent (AGR)</strong> is the yearly rental value of
          the land itself — excluding buildings and improvements. Scot-LAND&apos;s
          purpose is to make that figure visible for every place in Scotland as a
          research estimate, not an official valuation or bill. Figures pending
          sign-off; rents will appear only as ranges labelled market, proxy or
          shadow.
        </p>
        <p>
          A click on the map uses a <strong>Scot-LAND square reference</strong>{" "}
          for grid context. what3words lookup is a switched-off future adapter.
        </p>
      </section>

      <section id="rollup">
        <h2>The roll-up</h2>
        <p>
          The Scottish Government&apos;s data zones are the unit of account.
          Every natural capital value (surface, resource and eco) is meant to be
          apportioned to data zones and rolled up the official way:
        </p>
        <p>
          <strong>
            Data Zone 2022 (S01) → Intermediate Zone (S02) → Council Area (S12) →
            Scotland (S92)
          </strong>
        </p>
        <p>
          Roll-up uses the{" "}
          <a href={LOOKUP_URL} target="_blank" rel="noreferrer">
            Scottish Government Data Zone lookup 2022
          </a>{" "}
          under the{" "}
          <a href={LOOKUP_OGL} target="_blank" rel="noreferrer">
            Open Government Licence v3.0
          </a>
          , with no double counting. Health Board and electoral wards are
          optional extra geographies, not required for the national total.
        </p>
        <p className="downloads-note">
          Roll-up figures stay unpublished. For now, figures are published at
          Data Zone level only, not for individual parcels, plots or addresses.
        </p>
      </section>

      <section id="tags">
        <h2>The three tags</h2>
        <p>
          Every rent figure carries one confidence tag. Totals stay within one
          tag — never across tags or across price years.
        </p>
        <ul className="confidence-tag-list" data-testid="confidence-tag-list">
          {CONFIDENCE.map((row) => (
            <li key={row.kind}>
              <ConfidenceTag kind={row.kind} />
              <span className="confidence-tag-gloss">{row.gloss}</span>
            </li>
          ))}
        </ul>
        <p>
          Gaps use a grey hatch and the label <strong>No data</strong> — never
          filled with a placeholder rent.
        </p>
        <h3>Data-state quality tags</h3>
        <p>
          Inputs also carry a data-state quality tag (separate from market /
          proxy / shadow):
        </p>
        <ul className="quality-tag-list" data-testid="quality-tag-list">
          {QUALITY_TAGS.map((tag) => (
            <li key={tag}>
              <QualityTag quality={tag} />
              <span className="quality-tag-gloss">{QUALITY_TAG_GLOSS[tag]}</span>
            </li>
          ))}
        </ul>
      </section>

      <section id="rents">
        <h2>Rents kept separate; constraints add no value</h2>
        <p>
          Surface, resource and eco (nature) rents stay on separate rows. One
          rent per hectare per use. Planning uplift appears only as an
          &ldquo;of which&rdquo; note under surface land — never added as a
          sibling total.
        </p>
        <p>
          Designations, flood, crofting, land capability and similar overlays
          are labelled{" "}
          <strong>Constraint: changes best use, adds no value</strong>. They
          never show a rent figure.
        </p>
      </section>

      <section id="ledger" data-testid="methodology-ledger">
        <h2>Natural capital ledger</h2>
        <p>
          Full ledger rows and definitions. The map place card shows only the
          classes that apply at a point; this table is the complete account.
        </p>
        <div className="sources-table-wrap">
          <table className="sources-table" data-testid="methodology-ledger-table">
            <thead>
              <tr>
                <th scope="col">Row</th>
                <th scope="col">Class</th>
                <th scope="col">Tag</th>
                <th scope="col">Definition</th>
              </tr>
            </thead>
            <tbody>
              {LEDGER_FIXTURE_ROWS.map((row) => (
                <tr key={row.id} data-ledger-row={row.id}>
                  <td>{row.id}</td>
                  <td>{row.label}</td>
                  <td>{ledgerPublicTag(row.tag)}</td>
                  <td>
                    {row.id === "9"
                      ? "Offshore, outside the Scottish land total."
                      : row.id === "1a"
                        ? "Of which under surface land — never added as a sibling total."
                        : row.status_note}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p data-testid="methodology-oil-gas-footnote">
          <strong>Oil and gas</strong> — offshore, outside the Scottish land
          total.
        </p>
        <h3>Constraints</h3>
        <ul data-testid="methodology-ledger-constraints">
          {LEDGER_FIXTURE_CONSTRAINTS.map((c) => (
            <li key={c.id}>
              <strong>{c.label}</strong> — {c.rule}
            </li>
          ))}
        </ul>
      </section>

      <section id="sources">
        <h2>Sources</h2>
        <p>
          Every layer shows its licence in the legend on the map. The table
          below lists the catalog attribution lines. More detail and downloads
          live under <a href="/data">Data</a>,{" "}
          <a href="/downloads">Downloads</a> and the{" "}
          <a href={MINTLIFY.mapLayers} target="_blank" rel="noreferrer">
            map layer guide
          </a>
          .
        </p>
        <div className="sources-table-wrap">
          <table className="sources-table" data-testid="sources-table">
            <thead>
              <tr>
                <th scope="col">Layer / source</th>
                <th scope="col">Licence credit</th>
              </tr>
            </thead>
            <tbody>
              {LAYER_CREDITS.map((credit) => (
                <tr key={credit.layerId} data-layer-id={credit.layerId}>
                  <td>{credit.label}</td>
                  <td>
                    {credit.attribution}
                    {credit.licenceUrl ? (
                      <>
                        {" "}
                        <a
                          href={credit.licenceUrl}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Link
                        </a>
                      </>
                    ) : null}
                    {credit.nonCommercial ? " (non-commercial)" : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section id="gaps">
        <h2>Gaps</h2>
        <ul>
          <li>
            <strong>Roll-up not built yet</strong> — the Data Zone 2022 →
            Intermediate Zone → Council → Scotland roll-up is specified but not
            yet implemented in the engine. Roll-up figures stay unpublished.
          </li>
          <li>
            <strong>Surface rent still on Data Zone 2011</strong> — it needs a
            2011-to-2022 crosswalk (or a move onto DZ2022) before the official
            lookup can be applied end-to-end.
          </li>
          <li>
            Resource and eco values are not yet fully apportioned to data zones
            in the live store.
          </li>
          <li>
            Sasine / private ownership names beyond public records stay as
            visible gaps.
          </li>
        </ul>
        <p>
          Missing map cells use grey hatch and <strong>No data</strong>.
        </p>
      </section>

      <section id="validation">
        <h2>Validation</h2>
        <p>
          Figures stay internal until economic rules and yield calibration are
          signed off. The Valuation and Georgist bots check figures; the GIS bot
          checks every source and licence; CI must pass before merge.
          Publication grain remains: For now, figures are published at Data Zone
          level only, not for individual parcels, plots or addresses.
        </p>
        <p>
          API honesty rules (gaps as HTTP 503, never silent placeholders):{" "}
          <a href={MINTLIFY.apiReference} target="_blank" rel="noreferrer">
            API reference
          </a>
          .
        </p>
      </section>

      <section id="changelog">
        <h2>Changelog</h2>
        <ul>
          <li>
            <strong>2026-10-13</strong> — Mission and Methodology split from
            About (Designer brief v3.1). Confidence tags (market / proxy /
            shadow) with specified colours; constraint wording; sources table
            with licence credits; roll-up described as unpublished; open-data
            at launch line; Scot-LAND square reference naming.
          </li>
          <li>
            <strong>2026-10-13</strong> — AGR restored as site purpose on public
            About surfaces; Data Zone grain sentence fixed in charter and UI.
          </li>
        </ul>
        <p>
          Deeper method notes:{" "}
          <a href={MINTLIFY.introduction} target="_blank" rel="noreferrer">
            Mintlify introduction
          </a>
          .
        </p>
      </section>

      <p>
        <a href="/">Back to map</a>
        {" · "}
        <a href="/mission">Mission</a>
      </p>
    </main>
  );
}
