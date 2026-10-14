"use client";

import { useEffect, useState } from "react";
import { apiJson, engineVersionLine, type EngineStamp } from "../lib/api";

const DEVELOPMENT_NOTICE =
  "Research estimate. Figures are in development and may change as the engine improves.";

/** Footer stamp for the public map shell (no AGR £ breakdown). */
export function MapStampFooter() {
  const [stamp, setStamp] = useState<EngineStamp | null>(null);

  useEffect(() => {
    let active = true;
    apiJson<{ stamp?: EngineStamp | null }>("/health")
      .then((data) => {
        if (active) setStamp(data.stamp ?? null);
      })
      .catch(() => {
        if (active) setStamp(null);
      });
    return () => {
      active = false;
    };
  }, []);

  const versionLine = engineVersionLine(stamp);
  return (
    <footer className="map-footer">
      <p>{DEVELOPMENT_NOTICE}</p>
      {versionLine ? <p className="engine-stamp">{versionLine}</p> : null}
      <p className="map-footer-credit">
        <a href="/methodology">Sources and method</a>
        {" · "}
        Contains OS data © Crown copyright and database right 2026
        {" · "}
        Contains Royal Mail data © Royal Mail copyright and database right 2026
        {" · "}
        Source: Office for National Statistics licensed under the Open
        Government Licence v.3.0
        {" · "}
        No data provider endorses this site.
      </p>
    </footer>
  );
}

export default MapStampFooter;
