"use client";

import {
  sanitizePlaceStack,
  tagLabel,
  type PlaceHectareStackPayload,
  type PlaceStackRow,
  type PlaceStackSection,
} from "../lib/placeStack";

export type PlaceHectareStackProps = {
  data: PlaceHectareStackPayload | null;
  isLoading?: boolean;
  error?: string | null;
};

function StackRows({
  section,
  testId,
}: {
  section: PlaceStackSection;
  testId: string;
}) {
  return (
    <section
      className="place-stack-section"
      aria-label={section.label}
      data-testid={testId}
    >
      <h2 className="place-stack-section-title">{section.label}</h2>
      {section.unit ? (
        <p className="place-stack-unit">Unit: {section.unit}</p>
      ) : null}
      <ul className="place-stack-list" data-testid={`${testId}-rows`}>
        {section.rows.map((row) => (
          <StackRow key={row.id} row={row} />
        ))}
      </ul>
      <div
        className="place-stack-total"
        data-testid={`${testId}-total`}
        data-sum-ids={section.sum_row_ids.join(",")}
      >
        <span className="place-stack-total-label">
          Stack total ({section.sum_row_ids.join(" + ")})
        </span>
        <span
          className="place-stack-amount"
          title="Placeholder — not a published rent figure"
        >
          {section.total_placeholder}
        </span>
      </div>
      <p className="place-stack-note">{section.total_note}</p>
    </section>
  );
}

function StackRow({ row }: { row: PlaceStackRow }) {
  return (
    <li
      className={
        row.nested
          ? "place-stack-row place-stack-row-nested"
          : "place-stack-row"
      }
      data-testid={`place-stack-row-${row.id}`}
      data-nested={row.nested ? "true" : "false"}
      data-in-total={row.in_total ? "true" : "false"}
      data-stack={row.stack}
    >
      <div className="place-stack-row-bar" aria-hidden="true" />
      <div className="place-stack-row-main">
        <span className="place-stack-row-id">{row.id}</span>
        <span className="place-stack-row-label">{row.label}</span>
        <span className={`place-stack-tag tone-${row.tag}`}>
          {tagLabel(row.tag)}
        </span>
        <span
          className="place-stack-amount"
          data-testid={`place-stack-amount-${row.id}`}
          title="Placeholder — not a published rent figure"
        >
          {row.amount_placeholder}
        </span>
      </div>
      {row.nested ? (
        <p className="place-stack-nested-note" data-testid="place-stack-1a-note">
          Of which under surface land — not added into the headline total
        </p>
      ) : null}
      {!row.in_total && !row.nested && row.outside_scottish_total ? (
        <p className="place-stack-outside-note">
          Offshore, outside the Scottish land total
        </p>
      ) : null}
    </li>
  );
}

export function PlaceHectareStack({
  data,
  isLoading = false,
  error = null,
}: PlaceHectareStackProps) {
  const stack = data ? sanitizePlaceStack(data) : null;

  return (
    <article
      className="place-hectare-stack"
      data-testid="place-hectare-stack"
      aria-label="Per-hectare Annual Ground Rent breakdown"
    >
      {isLoading ? (
        <p className="place-stack-loading" aria-busy="true">
          Loading zone stack…
        </p>
      ) : null}

      {error ? (
        <p className="place-stack-error" role="alert">
          {error}
        </p>
      ) : null}

      {!isLoading && !error && stack && !stack.published ? (
        <div
          className="place-stack-blocked"
          data-testid="place-stack-blocked"
        >
          <h1>Zone not published</h1>
          <p>
            Data zone{" "}
            <code>{stack.zone.code}</code>
            {stack.zone.name ? ` (${stack.zone.name})` : ""} — nothing
            published for blocked zones.
          </p>
          <p className="place-stack-note">
            {stack.note || stack.publication_note}
          </p>
          <p className="place-stack-disclaimer">
            No modelled Annual Ground Rent. Land rent figures are not published
            yet.
          </p>
        </div>
      ) : null}

      {!isLoading && !error && stack && stack.published ? (
        <>
          <header className="place-stack-header">
            <p className="place-stack-kicker">Place · per hectare</p>
            <h1 className="place-stack-title">
              {stack.zone.name || stack.zone.code}
            </h1>
            <p className="place-stack-meta" data-testid="place-stack-zone">
              Data zone {stack.zone.code}
              {stack.zone.name ? ` · ${stack.zone.name}` : ""}
            </p>
            {stack.publication_note ? (
              <p
                className="place-stack-note"
                data-testid="place-stack-publication-note"
              >
                {stack.publication_note}
              </p>
            ) : null}
          </header>

          {stack.headline ? (
            <StackRows section={stack.headline} testId="place-stack-headline" />
          ) : null}

          {stack.shadow ? (
            <StackRows section={stack.shadow} testId="place-stack-shadow" />
          ) : null}

          {stack.outside ? (
            <section
              className="place-stack-section place-stack-outside"
              aria-label={stack.outside.label}
              data-testid="place-stack-outside"
            >
              <h2 className="place-stack-section-title">
                {stack.outside.label}
              </h2>
              <p className="place-stack-note">{stack.outside.note}</p>
              <ul className="place-stack-list">
                {stack.outside.rows.map((row) => (
                  <StackRow key={row.id} row={row} />
                ))}
              </ul>
              <h3 className="place-stack-subhead">Benchmarks</h3>
              <p className="place-stack-note" data-testid="place-stack-benchmark-label">
                {stack.outside.benchmark_label}
              </p>
              <ul
                className="place-stack-benchmarks"
                data-testid="place-stack-benchmarks"
              >
                {stack.outside.benchmarks.map((b) => (
                  <li key={b.id}>
                    <strong>{b.label}</strong>
                    <span className="place-stack-note"> — {b.note}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {stack.constraints ? (
            <section
              className="place-stack-section place-stack-constraints"
              aria-label="Constraints"
              data-testid="place-stack-constraints"
            >
              <h2 className="place-stack-section-title">Constraints</h2>
              <p className="place-stack-note">
                Constraint: changes best use, adds no value.
              </p>
              <ul className="place-stack-list">
                {stack.constraints.map((c) => (
                  <li
                    key={c.id}
                    className="place-stack-row place-stack-constraint"
                    data-testid={`place-stack-constraint-${c.id}`}
                  >
                    <div className="place-stack-row-main">
                      <span className="place-stack-row-label">{c.label}</span>
                      <span className="place-stack-tag tone-constraint">
                        {c.rule}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <p className="place-stack-disclaimer" data-testid="place-stack-disclaimer">
            Figures are being checked and aren&apos;t published yet.{" "}
            <a href="/methodology#calculation">How we value land</a>
            {stack.checks_url ? (
              <>
                {" · "}
                <a href={stack.checks_url}>Ledger checks</a>
              </>
            ) : null}
          </p>
        </>
      ) : null}

      {!isLoading && !error && !stack ? (
        <p className="place-stack-empty">
          Provide a Data Zone code to load the per-hectare stack.
        </p>
      ) : null}
    </article>
  );
}

export default PlaceHectareStack;
