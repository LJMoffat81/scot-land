import ScotlandMap from "@/components/ScotlandMap";

export default function HomePage() {
  return (
    <main>
      <h1 className="sr-only">
        Scot-LAND map: search a Scottish postcode or place
      </h1>
      <ScotlandMap />
    </main>
  );
}
