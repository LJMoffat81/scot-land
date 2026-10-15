import ScotlandMap from "@/components/ScotlandMap";

/** `/map` alias for the home map (MAP-CARDS URL contract E1). */
export default function MapPage() {
  return (
    <main>
      <h1 className="sr-only">
        Scot-LAND map: search a Scottish postcode or place
      </h1>
      <ScotlandMap />
    </main>
  );
}
