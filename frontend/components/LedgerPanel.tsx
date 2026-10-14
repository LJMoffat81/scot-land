"use client";

import { useEffect, useState } from "react";

import { visitorFacingError } from "@/lib/api";
import {
  fetchLedger,
  statusLabel,
  tagLabel,
  type LedgerPayload,
  type LedgerToggleState,
} from "@/lib/ledger";

export type LedgerPanelProps = {
  /** Controlled toggles for ledger rows + constraints (id → on). */
  enabled?: LedgerToggleState;
  defaultEnabled?: LedgerToggleState;
  onEnabledChange?: (next: LedgerToggleState) => void;
  /** Inject payload (tests / Story). Otherwise fetches GET /ledger (fixture fallback). */
  ledger?: LedgerPayload | null;
  className?: string;
  title?: string;
};

export default function LedgerPanel({
  enabled: controlled,
  defaultEnabled,
  onEnabledChange,
  ledger: ledgerProp,
  className,
  title = "Natural capital ledger",
}: LedgerPanelProps) {
  const [ledger, setLedger] = useState<LedgerPayload | null>(ledgerProp ?? null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(ledgerProp == null);
  const [internalEnabled, setInternalEnabled] = useState<LedgerToggleState>(
    () => defaultEnabled ?? {},
  );

  const enabled = controlled ?? internalEnabled;

  useEffect(() => {
    if (ledgerProp !== undefined) {
      setLedger(ledgerProp);
      setLoading(false);
      setLoadError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetchLedger()
      .then((payload) => {
        if (!cancelled) {
          setLedger(payload);
          setLoadError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLedger(null);
          setLoadError(visitorFacingError(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ledgerProp]);

  const setEnabled = (id: string, on: boolean) => {
    const next = { ...enabled, [id]: on };
    if (controlled === undefined) setInternalEnabled(next);
    onEnabledChange?.(next);
  };

  return (
    <aside
      className={["ledger-panel", className].filter(Boolean).join(" ")}
      aria-label={title}
      data-testid="ledger-panel"
    >
      <p className="hud-tools-title">{title}</p>
      <p className="layer-meta" data-testid="ledger-panel-lead">
        One row per natural-capital rent class. Toggle paints where that row
        applies. Constraints change best use and add no value. Figures are
        being checked and aren't published yet.
      </p>

      {loading && (
        <p className="layer-meta" data-testid="ledger-panel-loading">
          Loading ledger…
        </p>
      )}
      {loadError && (
        <p className="error-line" data-testid="ledger-panel-error">
          {loadError}
        </p>
      )}

      {!loading && !loadError && ledger && (
        <>
          <p className="layer-meta" data-testid="ledger-publication-note">
            {ledger.publication_note}
          </p>
          {ledger.source === "fixture" && (
            <p className="layer-meta" data-testid="ledger-source-fixture">
              Using sample ledger data until <code>/ledger</code> is live.
            </p>
          )}

          <section
            className="ledger-panel-group"
            aria-label="Ledger rows"
            data-testid="ledger-rows"
          >
            <label className="layer-select-label">Ledger rows</label>
            <ul className="ledger-panel-list">
              {ledger.rows.map((row) => {
                const on = Boolean(enabled[row.id]);
                return (
                  <li
                    key={row.id}
                    className={
                      row.nested
                        ? "ledger-panel-row ledger-panel-row-nested"
                        : "ledger-panel-row"
                    }
                    data-testid={`ledger-row-${row.id}`}
                    data-status={row.status}
                    data-nested={row.nested ? "true" : "false"}
                  >
                    <div className="ledger-panel-row-head">
                      <button
                        type="button"
                        className={on ? "chip active" : "chip"}
                        data-testid={`ledger-toggle-${row.id}`}
                        aria-pressed={on}
                        title={row.status_note}
                        onClick={() => setEnabled(row.id, !on)}
                      >
                        <span className="ledger-row-id">{row.id}</span>
                        {row.label}
                      </button>
                      <span
                        className={`ledger-panel-tag tone-${row.tag}`}
                        data-testid={`ledger-tag-${row.id}`}
                      >
                        {tagLabel(row.tag)}
                      </span>
                      <span
                        className={`ledger-panel-status tone-${row.status}`}
                        data-testid={`ledger-status-${row.id}`}
                      >
                        {statusLabel(row.status)}
                      </span>
                      <span
                        className="ledger-panel-amount"
                        data-testid={`ledger-amount-${row.id}`}
                        title="Placeholder — not a published rent figure"
                      >
                        {row.amount_placeholder}
                      </span>
                    </div>
                    {row.outside_scottish_total && (
                      <p
                        className="ledger-panel-note"
                        data-testid={`ledger-outside-${row.id}`}
                      >
                        Offshore, outside the Scottish land total
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>

          <section
            className="ledger-panel-group ledger-constraints"
            aria-label="Constraints"
            data-testid="ledger-constraints"
          >
            <label className="layer-select-label">Constraints</label>
            <p className="layer-meta" data-testid="ledger-constraints-rule">
              Constraint: changes best use, adds no value
            </p>
            <ul className="ledger-panel-list">
              {ledger.constraints.map((constraint) => {
                const on = Boolean(enabled[constraint.id]);
                return (
                  <li
                    key={constraint.id}
                    className="ledger-panel-row"
                    data-testid={`ledger-constraint-${constraint.id}`}
                  >
                    <div className="ledger-panel-row-head">
                      <button
                        type="button"
                        className={on ? "chip active" : "chip"}
                        data-testid={`ledger-constraint-toggle-${constraint.id}`}
                        aria-pressed={on}
                        title={constraint.rule}
                        onClick={() => setEnabled(constraint.id, !on)}
                      >
                        {constraint.label}
                      </button>
                      <span
                        className="ledger-panel-status tone-constraint"
                        data-testid={`ledger-constraint-rule-${constraint.id}`}
                      >
                        {constraint.rule}
                      </span>
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
        </>
      )}
    </aside>
  );
}
