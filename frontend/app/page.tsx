"use client";

import { useEffect, useState } from "react";
import ScotlandMap from "@/components/ScotlandMap";
import { apiJson, engineVersionLine, type EngineStamp } from "@/lib/api";

export default function HomePage() {
  const [versionLine, setVersionLine] = useState("");

  useEffect(() => {
    let active = true;
    apiJson<{ stamp?: EngineStamp | null }>("/health")
      .then((data) => {
        if (active) setVersionLine(engineVersionLine(data.stamp));
      })
      .catch(() => {
        if (active) setVersionLine("");
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <>
      <ScotlandMap />
      <footer
        style={{
          position: "fixed",
          left: 0,
          right: 0,
          bottom: 0,
          zIndex: 6,
          background: "rgba(255,255,255,0.96)",
          textAlign: "center",
          padding: "0.35rem 0.8rem",
        }}
      >
        <p className="meta" style={{ margin: 0 }}>
          Research estimate. Figures are in development and may change as the engine improves.
        </p>
        {versionLine ? <p className="engine-stamp">{versionLine}</p> : null}
      </footer>
    </>
  );
}
