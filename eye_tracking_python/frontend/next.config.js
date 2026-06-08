/** @type {import('next').NextConfig} */

// In development the Next.js dev server proxies /api/* to the local FastAPI
// backend so the browser talks to a single origin (no CORS friction).
// Override the target with PDEYE_BACKEND_URL if your backend runs elsewhere.
const BACKEND_URL = process.env.PDEYE_BACKEND_URL || "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
