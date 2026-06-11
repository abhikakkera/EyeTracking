import Link from "next/link";
import { SHORT_DISCLAIMER } from "@/lib/constants";

export default function Footer() {
  return (
    <footer className="footer">
      <div className="container">
        <div className="footer-grid">
          <div style={{ maxWidth: 320 }}>
            <div className="brand" style={{ marginBottom: 10 }}>
              <span className="brand-mark" aria-hidden />
              Ocula
            </div>
            <p className="small" style={{ margin: 0 }}>
              Eye movement tracking, made simple. A research prototype for
              eye-tracking data collection — your data stays on your computer.
            </p>
          </div>

          <div>
            <h4>Product</h4>
            <Link href="/test">Activities</Link>
            <Link href="/dashboard">Dashboard</Link>
            <Link href="/history">Results</Link>
          </div>

          <div>
            <h4>Learn</h4>
            <Link href="/about">About</Link>
            <Link href="/research">Research</Link>
          </div>

          <div>
            <h4>Account</h4>
            <Link href="/login">Log in</Link>
            <Link href="/signup">Sign up</Link>
          </div>
        </div>

        <p className="small muted" style={{ margin: "0 0 6px", maxWidth: "70ch" }}>
          {SHORT_DISCLAIMER}
        </p>
        <p className="small" style={{ margin: 0, color: "var(--gray-soft)" }}>
          © {new Date().getFullYear()} Ocula · Research prototype · Data stays local
        </p>
      </div>
    </footer>
  );
}
