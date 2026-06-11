import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { AuthProvider } from "@/lib/auth";

export const metadata: Metadata = {
  title: "Ocula — Eye movement tracking, made simple",
  description:
    "Ocula guides you through short visual activities and records eye movement " +
    "patterns with your camera. A research prototype for eye-tracking data " +
    "collection — not a medical device.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <Navbar />
          <main>{children}</main>
          <Footer />
        </AuthProvider>
      </body>
    </html>
  );
}
