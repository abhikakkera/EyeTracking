import Link from "next/link";
import Hero from "@/components/Hero";
import FeatureCard from "@/components/FeatureCard";
import DisclaimerBox from "@/components/DisclaimerBox";
import { ACTIVITIES } from "@/lib/constants";

export default function HomePage() {
  return (
    <>
      <Hero />

      {/* How it works */}
      <section className="section">
        <div className="container">
          <div className="center" style={{ maxWidth: 640, margin: "0 auto 40px" }}>
            <span className="eyebrow">How it works</span>
            <h2>Four simple steps</h2>
            <p>
              No special hardware — just your webcam and a few minutes. Everything
              runs locally on your computer.
            </p>
          </div>
          <div className="grid grid-4">
            <FeatureCard icon="①" title="Choose an activity">
              Pick one of four short dot-following activities.
            </FeatureCard>
            <FeatureCard icon="②" title="Quick camera check">
              We help you frame your face and check your lighting.
            </FeatureCard>
            <FeatureCard icon="③" title="Follow the dots">
              The activity window opens and guides you in real time.
            </FeatureCard>
            <FeatureCard icon="④" title="Review your data">
              Clear, friendly results appear here when you finish.
            </FeatureCard>
          </div>
        </div>
      </section>

      {/* What the activities measure */}
      <section className="section section-soft">
        <div className="container">
          <div className="center" style={{ maxWidth: 640, margin: "0 auto 40px" }}>
            <span className="eyebrow">What the activities measure</span>
            <h2>Eye movement patterns, captured carefully</h2>
            <p>
              Each activity observes a different aspect of how the eyes move.
              These are research measures of movement — not health assessments.
            </p>
          </div>
          <div className="grid grid-4">
            {ACTIVITIES.map((a) => (
              <div className="card" key={a.slug}>
                <div className="ic" aria-hidden style={{ marginBottom: 12 }}>
                  {a.icon}
                </div>
                <h3 style={{ fontSize: "1.05rem" }}>{a.name}</h3>
                <p className="small" style={{ marginBottom: 0 }}>
                  {a.measures}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Research vision */}
      <section className="section">
        <div className="container grid grid-2" style={{ alignItems: "center", gap: 40 }}>
          <div>
            <span className="eyebrow">Research vision</span>
            <h2>Built to support research, not to replace clinicians</h2>
            <p>
              Eye movement patterns are an active area of neurological research.
              PDEYE&apos;s role today is <strong>data collection and movement
              analysis</strong> — measuring things like response time, fixation
              stability, smooth pursuit, and saccade patterns.
            </p>
            <p>
              Any future clinically validated model would require large clinical
              datasets, independent validation, regulatory review, and oversight
              by qualified healthcare professionals. PDEYE is not a diagnostic
              tool.
            </p>
            <Link className="btn btn-secondary mt-2" href="/research">
              Read about the research →
            </Link>
          </div>
          <div className="card" style={{ background: "var(--bg-softer)" }}>
            <h3>What PDEYE does</h3>
            <ul className="checklist" style={{ marginTop: 14 }}>
              <li>
                <span className="tick ok">✓</span>
                <span>Records eye movement during structured activities</span>
              </li>
              <li>
                <span className="tick ok">✓</span>
                <span>Reports task performance and tracking quality</span>
              </li>
              <li>
                <span className="tick ok">✓</span>
                <span>Saves research-grade data exports locally</span>
              </li>
              <li>
                <span className="tick pending">✕</span>
                <span className="muted">
                  Does not diagnose, predict, or screen for any condition
                </span>
              </li>
            </ul>
          </div>
        </div>
      </section>

      {/* Privacy + Limitations + Roadmap */}
      <section className="section section-soft">
        <div className="container">
          <div className="grid grid-3">
            <div className="card">
              <div className="ic" aria-hidden style={{ marginBottom: 12 }}>
                🔒
              </div>
              <h3>Privacy &amp; data storage</h3>
              <p className="small">
                By default, PDEYE stores results locally on your computer. Raw
                eye-tracking files and session summaries are saved in the local
                project folder unless you choose to export them. Cloud syncing is
                not enabled in this prototype.
              </p>
            </div>
            <div className="card">
              <div className="ic" aria-hidden style={{ marginBottom: 12 }}>
                ⚖️
              </div>
              <h3>Limitations</h3>
              <p className="small">
                PDEYE uses a standard webcam, so tracking quality depends on your
                camera, lighting, and distance. It has not been clinically
                validated. Results describe eye movement during the activities —
                nothing more.
              </p>
            </div>
            <div className="card">
              <div className="ic" aria-hidden style={{ marginBottom: 12 }}>
                🧭
              </div>
              <h3>Future roadmap</h3>
              <p className="small">
                Planned work includes more activities, optional calibration,
                richer visualizations, and contributing anonymized data to
                Parkinson&apos;s-related research — always under appropriate
                validation and oversight.
              </p>
            </div>
          </div>

          <div className="mt-4">
            <DisclaimerBox />
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="section">
        <div className="container center" style={{ maxWidth: 620 }}>
          <h2>Ready to try an activity?</h2>
          <p>It takes just a couple of minutes and runs entirely on your machine.</p>
          <div className="row" style={{ justifyContent: "center", marginTop: 8 }}>
            <Link className="btn btn-primary btn-lg" href="/test">
              Start an Eye Movement Session
            </Link>
            <Link className="btn btn-ghost btn-lg" href="/history">
              View previous results
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
