import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Get desktop shortcuts",
};

/** Public page — no login required. Big download for Start/Stop on this PC. */
export default function GetDesktopPage() {
  return (
    <div className="login-shell">
      <div className="login-panel rise desktop-download-panel">
        <h1>Put Argus on this PC</h1>
        <p className="lede">
          Download the installer, then double-click it. That adds{" "}
          <strong>Start Argus</strong> and <strong>Stop Argus</strong> to your
          Desktop.
        </p>

        <a
          className="btn control-btn control-btn-desktop desktop-download-cta"
          href="/api/founder/desktop-installer"
          download="Install-Argus-Desktop.cmd"
        >
          Download desktop installer
        </a>

        <ol className="desktop-download-steps">
          <li>Click the button above (saves <code>Install-Argus-Desktop.cmd</code>).</li>
          <li>Open your Downloads folder.</li>
          <li>Double-click the file (Allow if Windows asks).</li>
          <li>Use <strong>Start Argus</strong> / <strong>Stop Argus</strong> on your Desktop.</li>
        </ol>

        <p className="muted-note">
          Live trading stays locked. Paper trading only.
        </p>

        <div className="form-actions" style={{ marginTop: "1.25rem" }}>
          <Link className="btn secondary" href="/login">
            Back to sign in
          </Link>
          <Link className="btn secondary" href="/today">
            Open Today
          </Link>
        </div>
      </div>
    </div>
  );
}
