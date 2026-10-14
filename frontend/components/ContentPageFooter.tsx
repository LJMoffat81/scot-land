"use client";

import { useEffect, useState } from "react";
import { apiJson, engineVersionLine, type EngineStamp } from "../lib/api";

/** Shared content-page footer (site-watch PR A item 4). */
export function ContentPageFooter() {
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
    <footer className="content-page-footer" data-testid="content-page-footer">
      <p data-testid="content-page-footer-line">
        Research estimate · Open data ·{" "}
        <a href="/data#licences">Sources and licences</a>
      </p>
      {versionLine ? <p className="engine-stamp">{versionLine}</p> : null}
      <p>
        Contains OS data © Crown copyright and database right 2026
        {" · "}
        Contains Royal Mail data © Royal Mail copyright and database right 2026
        {" · "}
        Source: Office for National Statistics licensed under the Open
        Government Licence v.3.0
        {" · "}
        Map tiles ©{" "}
        <a
          href="https://openfreemap.org/"
          target="_blank"
          rel="noopener noreferrer"
        >
          OpenFreeMap
        </a>
        {" / "}
        <a
          href="https://www.openstreetmap.org/copyright"
          target="_blank"
          rel="noopener noreferrer"
        >
          OpenStreetMap
        </a>{" "}
        contributors
        {" · "}
        No data provider endorses this site.
      </p>
    </footer>
  );
}

export default ContentPageFooter;
