import Link from "next/link";
import DisclaimerBox from "@/components/DisclaimerBox";
import { SHORT_DISCLAIMER } from "@/lib/constants";

export default function Hero() {
  return (
    <section className="hero">
      <div className="container hero-grid">
        <div className="fade-up">
          <span className="eyebrow">Research-grade eye tracking</span>
          <h1>PDEYE</h1>
          <p className="lead">
            Eye movement tracking for research-grade digital health insights.
          </p>
          <p className="desc">
            PDEYE records how your eyes move during simple dot-following
            activities. The platform is designed to collect high-quality eye
            movement data for research into neurological movement patterns,
            including Parkinson&apos;s-related research.
          </p>

          <div className="hero-actions">
            <Link className="btn btn-primary btn-lg" href="/test">
              Start an Eye Movement Session
            </Link>
            <Link className="btn btn-secondary btn-lg" href="/history">
              View Previous Results
            </Link>
            <Link className="btn btn-ghost btn-lg" href="/research">
              Learn About the Research
            </Link>
          </div>

          <div style={{ maxWidth: 560, marginTop: 18 }}>
            <DisclaimerBox compact text={SHORT_DISCLAIMER} />
          </div>
        </div>

        <div className="hero-visual fade-up" aria-hidden>
          <div className="crosshair" />
          <div className="target" />
          <div className="gaze-dot" />
        </div>
      </div>
    </section>
  );
}
