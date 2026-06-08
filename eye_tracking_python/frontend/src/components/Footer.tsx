import Link from "next/link";
import { SHORT_DISCLAIMER } from "@/lib/constants";

export default function Footer() {
  return (
    <footer className="footer">
      <div className="container">
        <div className="footer-grid">
          <div style={{ maxWidth: 320 }}>
            <div className="brand" style={{ marginBottom: 10 }}>
              <span className="logo" aria-hidden>
                ◉
              </span>
              PDEYE
            </div>
            <p className="small muted" style={{ marginBottom: 0 }}>
              Eye movement tracking for research-grade digital health insights.
              Local-first. Your data stays on your computer.
            </p>
          </div>

          <div>
            <h4>Product</h4>
            <Link href="/test">Activities</Link>
            <Link href="/history">Session history</Link>
            <Link href="/results">Latest results</Link>
          </div>

          <div>
            <h4>Learn</h4>
            <Link href="/research">The research</Link>
            <Link href="/about">About &amp; privacy</Link>
          </div>
        </div>

        <p className="small muted" style={{ marginBottom: 0 }}>
          {SHORT_DISCLAIMER}
        </p>
      </div>
    </footer>
  );
}
