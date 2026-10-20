import type { NextConfig } from "next";

// The browser (laptop or phone) only ever talks to this Next.js server.
// API calls go to /api/* here and are proxied to the FastAPI backend, so the
// backend can stay on localhost and no IP addresses need to be hard-coded.
const BACKEND_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Self-contained server.js for the Docker image (see /Dockerfile).
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
};

export default nextConfig;
