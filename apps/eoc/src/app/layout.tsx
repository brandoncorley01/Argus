import type { Metadata } from "next";
import { IBM_Plex_Sans, IBM_Plex_Serif } from "next/font/google";

import "./globals.css";

const sans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-sans-loaded",
  display: "swap",
});

const display = IBM_Plex_Serif({
  subsets: ["latin"],
  weight: ["500", "600"],
  variable: "--font-display-loaded",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Argus · Executive Operations Center",
    template: "%s · Argus EOC",
  },
  description:
    "Institutional command center for Argus control-plane operations. Real backend state only.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${sans.variable} ${display.variable}`}>
      <body
        style={{
          fontFamily: "var(--font-sans-loaded), var(--font-sans)",
          ["--font-display" as string]:
            "var(--font-display-loaded), Georgia, serif",
          ["--font-sans" as string]:
            "var(--font-sans-loaded), 'Segoe UI', sans-serif",
        }}
      >
        <a className="skip-link" href="#main">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
