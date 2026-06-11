import Link from "next/link";
import Hero from "@/components/Hero";
import DisclaimerBox from "@/components/DisclaimerBox";

const STEPS = [
  {
    n: 1,
    title: "Set up your camera",
    body: "A short check helps you frame your face, distance, and lighting before you begin.",
  },
  {
    n: 2,
    title: "Follow simple dots",
    body: "Each activity shows a dot to look toward, away from, or follow. It runs right in the page.",
  },
  {
    n: 3,
    title: "Review your eye movement summary",
    body: "When you finish, Ocula builds a clear, human summary of how your eyes moved.",
  },
  {
    n: 4,
    title: "Save results to your account",
    body: "Every session is saved to your account so you can look back over time.",
  },
];

const MEASURES = [
  { title: "Response timing", body: "How quickly the eyes move when a new dot appears." },
  { title: "Gaze stability", body: "How steadily the eyes hold on a fixed point." },
  { title: "Smooth following", body: "How closely the eyes track a moving target." },
  { title: "Tracking quality", body: "How clearly the camera could see your eyes." },
  { title: "Blink activity", body: "How often blinks occur during a session." },
];

export default function HomePage() {
  return (
    <>
      <Hero />

      {/* How it works */}
      <section className="section">
        <div className="container">
          <div style={{ maxWidth: 620, marginBottom: 44 }}>
            <span className="eyebrow">How it works</span>
            <h2>From camera to summary in a few minutes.</h2>
            <p className="lead">
              No special hardware — just your webcam. Everything runs locally on
              your computer.
            </p>
          </div>
          <div className="steps-flow">
            {STEPS.map((s) => (
              <div className="flow-step" key={s.n}>
                <div className="flow-num">{s.n}</div>
                <div>
                  <h3>{s.title}</h3>
                  <p>{s.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* What Ocula measures */}
      <section className="section section-soft section-line">
        <div className="container">
          <div style={{ maxWidth: 620, marginBottom: 40 }}>
            <span className="eyebrow">What Ocula measures</span>
            <h2>A few clear signals from how the eyes move.</h2>
            <p className="lead">
              Each activity observes one aspect of eye movement. These are
              research measures — not health assessments.
            </p>
          </div>
          <div className="grid grid-5">
            {MEASURES.map((m) => (
              <div className="tile" key={m.title}>
                <h3>{m.title}</h3>
                <p>{m.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Why it matters */}
      <section className="section">
        <div className="container grid grid-2" style={{ alignItems: "center", gap: 52 }}>
          <div>
            <span className="eyebrow">Why it matters</span>
            <h2>Clean data first. Conclusions later, and carefully.</h2>
            <div className="prose">
              <p>
                Eye movement can reveal subtle patterns in attention, timing, and
                movement control. Researchers study these patterns in many
                neurological conditions, including Parkinson&apos;s disease.
              </p>
              <p>
                Ocula focuses on collecting clean, structured eye movement data —
                <strong> not making medical conclusions</strong>. Any future
                clinically validated tool would require clinical datasets,
                independent validation, regulatory review, and oversight by
                qualified healthcare professionals.
              </p>
            </div>
            <Link className="btn btn-secondary mt-2" href="/research">
              Read about the research →
            </Link>
          </div>
          <div className="card" style={{ background: "var(--bg-softer)" }}>
            <h3 style={{ marginBottom: 16 }}>What Ocula does — and doesn&apos;t</h3>
            <ul className="checklist">
              <li>
                <span className="tick ok">✓</span>
                <span>Records eye movement during structured activities</span>
              </li>
              <li>
                <span className="tick ok">✓</span>
                <span>Reports tracking quality and a friendly summary</span>
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

      {/* Privacy */}
      <section className="section section-soft section-line">
        <div className="container grid grid-2" style={{ gap: 52, alignItems: "start" }}>
          <div>
            <span className="eyebrow">Privacy</span>
            <h2>Your sessions stay on your computer.</h2>
            <p className="lead-xl maxw-ch">
              Camera frames are processed locally by the Ocula backend in this
              prototype. Raw video is not saved unless debug recording is enabled
              — Ocula keeps the extracted eye-movement data and session summaries.
            </p>
          </div>
          <div className="grid" style={{ gap: 14 }}>
            <div className="tile">
              <h3>Local by default</h3>
              <p>Results and exports are written to the local project folder. Cloud syncing is not enabled.</p>
            </div>
            <div className="tile">
              <h3>You control exports</h3>
              <p>Download your research data as CSV/JSON whenever you like, from your results.</p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="section">
        <div className="container center" style={{ maxWidth: 620 }}>
          <h2>Ready to try a session?</h2>
          <p className="lead">It takes a couple of minutes and runs entirely on your machine.</p>
          <div className="row" style={{ justifyContent: "center", marginTop: 12 }}>
            <Link className="btn btn-primary btn-lg" href="/signup">
              Create your account
            </Link>
            <Link className="btn btn-ghost btn-lg" href="/login">
              Log in
            </Link>
          </div>
          <div className="mt-4" style={{ textAlign: "left" }}>
            <DisclaimerBox />
          </div>
        </div>
      </section>
    </>
  );
}
