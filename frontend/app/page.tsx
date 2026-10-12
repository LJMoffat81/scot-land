import ScotlandMap from "@/components/ScotlandMap";

export default function HomePage() {
  return (
    <main>
      <h1 className="sr-only">
        Scot-LAND map: search a Scottish postcode, place or coordinates
      </h1>
      <ScotlandMap />
    </main>
  );
}
