import DisclaimerBox from "@/components/DisclaimerBox";
import Link from "next/link";

export const metadata = {
  title: "About & privacy — PDEYE",
};

export default function AboutPage() {
  return (
    <section className="section">
      <div className="container" style={{ maxWidth: 820 }}>
        <span className="eyebrow">About PDEYE</span>
        <h1>A local-first research prototype</h1>
        <p className="lead" style={{ color: "var(--ink)", maxWidth: "none" }}>
          PDEYE turns a standard webcam into an eye movement data-collection tool
          for research — running entirely on your own computer.
        </p>

        <div className="card mt-3">
          <h3>What PDEYE is</h3>
          <p>
            PDEYE records how your eyes move during short, structured
            dot-following activities and reports clear, friendly summaries of the
            results. It is built for research and personal curiosity about eye
            movement. It is a research prototype, not a medical device, and not a
            diagnostic tool.
          </p>
        </div>

        <div className="card mt-3">
          <h3>Privacy &amp; data storage</h3>
          <p>
            By default, PDEYE stores results locally on your computer. Raw
            eye-tracking files and session summaries are saved in the local
            project folder unless you choose to export them. Cloud syncing is not
            enabled in this prototype, and no account is required.
          </p>
          <p className="small muted" style={{ marginBottom: 0 }}>
            Note: PDEYE does not claim HIPAA compliance or any regulatory
            certification. Please handle any recorded data responsibly.
          </p>
        </div>

        <div className="card mt-3">
          <h3>Limitations</h3>
          <ul className="checklist" style={{ marginTop: 4 }}>
            <li>
              <span className="tick pending">•</span>
              <span>
                Webcam-based tracking quality depends on your camera, lighting,
                and distance.
              </span>
            </li>
            <li>
              <span className="tick pending">•</span>
              <span>
                Results describe eye movement during the activities — they are not
                health assessments.
              </span>
            </li>
            <li>
              <span className="tick pending">•</span>
              <span>
                The software has not been clinically validated and is for research
                use only.
              </span>
            </li>
          </ul>
        </div>

        <div className="card mt-3">
          <h3>How it works under the hood</h3>
          <p className="small">
            A local backend launches the eye-tracking activity, which records data
            and saves standard CSV/JSON exports. The website reads those files and
            presents friendly summaries. Nothing leaves your machine unless you
            export it yourself.
          </p>
        </div>

        <div className="mt-3">
          <DisclaimerBox />
        </div>

        <div className="row mt-3">
          <Link className="btn btn-primary" href="/test">
            Start an activity
          </Link>
          <Link className="btn btn-ghost" href="/research">
            Read about the research
          </Link>
        </div>
      </div>
    </section>
  );
}
