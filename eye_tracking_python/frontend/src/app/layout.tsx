import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";

export const metadata: Metadata = {
  title: "PDEYE — Eye movement tracking for research",
  description:
    "PDEYE records how your eyes move during simple dot-following activities to " +
    "collect high-quality eye movement data for research. Research prototype — " +
    "not a medical device.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Navbar />
        <main>{children}</main>
        <Footer />
      </body>
    </html>
  );
}
