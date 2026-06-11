import DisclaimerBox from "@/components/DisclaimerBox";
import Link from "next/link";

export const metadata = {
  title: "The research — Ocula",
};

export default function ResearchPage() {
  return (
    <section className="section">
      <div className="container" style={{ maxWidth: 820 }}>
        <span className="eyebrow">Background &amp; research</span>
        <h1>Eye movement and neurological research</h1>
        <p className="lead" style={{ color: "var(--ink)", maxWidth: "none" }}>
          A plain-language overview of why eye movement is studied — and exactly
          what Ocula does and does not do.
        </p>

        <div className="card mt-3">
          <h3>About Parkinson&apos;s disease</h3>
          <p>
            Parkinson&apos;s disease is a condition that affects movement. It can
            involve motor symptoms (such as changes in movement and coordination)
            and non-motor symptoms. It is diagnosed and managed by qualified
            healthcare professionals using clinical assessment and established
            medical tools. Ocula plays no part in that process.
          </p>
        </div>

        <div className="card mt-3">
          <h3>Why study eye movement?</h3>
          <p>
            Eye movements are a rich, measurable form of motor behavior, and
            patterns in eye movement are an active area of neurological research.
            Researchers use eye-tracking to study things like:
          </p>
          <ul className="checklist" style={{ marginTop: 10 }}>
            <li>
              <span className="tick ok">✓</span>
              <span>
                <strong>Response time</strong> — how quickly the eyes react to a
                new target
              </span>
            </li>
            <li>
              <span className="tick ok">✓</span>
              <span>
                <strong>Fixation stability</strong> — how steadily the eyes hold
                still
              </span>
            </li>
            <li>
              <span className="tick ok">✓</span>
              <span>
                <strong>Smooth pursuit</strong> — how smoothly the eyes follow a
                moving target
              </span>
            </li>
            <li>
              <span className="tick ok">✓</span>
              <span>
                <strong>Saccade patterns</strong> — the rapid jumps the eyes make
                between points
              </span>
            </li>
          </ul>
        </div>

        <div className="card mt-3">
          <h3>Ocula&apos;s current role</h3>
          <p>
            Ocula is a research prototype for <strong>eye movement data
            collection and movement analysis</strong>. It measures task
            performance and tracking quality during simple activities. It does
            not diagnose, treat, predict, or screen for Parkinson&apos;s disease
            or any other condition, and it does not produce any medical or risk
            assessment. It is not a diagnostic tool.
          </p>
        </div>

        <div className="card mt-3">
          <h3>What a future research tool would require</h3>
          <p>
            Turning eye movement data into anything clinically meaningful is a
            long road. A future clinically validated model would require large,
            well-labeled clinical datasets, independent validation studies,
            regulatory review, and ongoing oversight by qualified healthcare
            professionals. Until then, Ocula is strictly a data-collection
            instrument for Parkinson&apos;s-related research and general eye
            movement research.
          </p>
        </div>

        <div className="card mt-3">
          <h3>Sources to add later</h3>
          <p className="small">
            The organizations below are reputable starting points for
            general information on Parkinson&apos;s disease and movement research.
            These are <strong>suggested sources only</strong> — specific links and
            peer-reviewed citations should be verified by a qualified reviewer
            before any public release.
          </p>
          <ul className="checklist" style={{ marginTop: 10 }}>
            <li>
              <span className="tick pending">•</span>
              <span>
                National Institute of Neurological Disorders and Stroke (NIH /
                NINDS)
              </span>
            </li>
            <li>
              <span className="tick pending">•</span>
              <span>Parkinson&apos;s Foundation</span>
            </li>
            <li>
              <span className="tick pending">•</span>
              <span>The Michael J. Fox Foundation</span>
            </li>
            <li>
              <span className="tick pending">•</span>
              <span>
                Peer-reviewed eye-tracking and Parkinson&apos;s research
                publications (to be cited individually)
              </span>
            </li>
          </ul>
        </div>

        <div className="mt-3">
          <DisclaimerBox />
        </div>

        <div className="row mt-3">
          <Link className="btn btn-primary" href="/test">
            Try an activity
          </Link>
          <Link className="btn btn-ghost" href="/about">
            About &amp; privacy
          </Link>
        </div>
      </div>
    </section>
  );
}
