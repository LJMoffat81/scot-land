import ResearchBanner from "@/components/ResearchBanner";
import SiteNav from "@/components/SiteNav";
import {
  DEVELOPERS_GLOSSARY_TERMS,
  DEVELOPERS_GLOSSARY_TITLE,
} from "@/lib/developersGlossary";

/**
 * Developer glossary — linked only from /developers.
 * The HTML guard strips [data-testid="developers-glossary"] before the shadow ban.
 */
export default function DevelopersGlossaryPage() {
  return (
    <main
      className="downloads-page developers-page developers-glossary-page"
      data-testid="developers-glossary-page"
    >
      <SiteNav current="developers" />
      <h1>{DEVELOPERS_GLOSSARY_TITLE}</h1>
      <ResearchBanner />
      <p className="downloads-note">
        Words used in our method and in the data for developers. Overview:{" "}
        <a href="/developers">Get the data</a>.
      </p>
      <div
        className="developers-glossary-list"
        data-testid="developers-glossary"
      >
        {DEVELOPERS_GLOSSARY_TERMS.map((entry) => {
          const headingId = `glossary-${entry.term
            .toLowerCase()
            .replace(/\s+/g, "-")}`;
          return (
            <section
              key={entry.term}
              className="developers-glossary-item"
              data-testid={`glossary-term-${entry.term}`}
              aria-labelledby={headingId}
            >
              <h2 id={headingId}>{entry.term}</h2>
              <p>
                {entry.chip ? (
                  <>
                    <span className="downloads-note">{entry.chip}</span>{" "}
                  </>
                ) : null}
                {entry.definition}
              </p>
            </section>
          );
        })}
      </div>
    </main>
  );
}
