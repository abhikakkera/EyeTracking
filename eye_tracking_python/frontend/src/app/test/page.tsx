import TestCard from "@/components/TestCard";
import DisclaimerBox from "@/components/DisclaimerBox";
import { ACTIVITIES } from "@/lib/constants";

export const metadata = {
  title: "Choose an activity — Ocula",
};

export default function TestSelectionPage() {
  return (
    <section className="section">
      <div className="container">
        <div style={{ maxWidth: 680, marginBottom: 36 }}>
          <span className="eyebrow">Eye movement activities</span>
          <h1 style={{ fontSize: "2.4rem" }}>Choose an activity</h1>
          <p>
            Each activity is a short, guided dot-following task. Friendly names
            are shown first, with the research term underneath. Pick one to begin
            — you&apos;ll do a quick camera check next.
          </p>
        </div>

        <div className="grid grid-2 gap-lg">
          {ACTIVITIES.map((a) => (
            <TestCard key={a.slug} activity={a} />
          ))}
        </div>

        <div className="mt-4">
          <DisclaimerBox />
        </div>
      </div>
    </section>
  );
}
