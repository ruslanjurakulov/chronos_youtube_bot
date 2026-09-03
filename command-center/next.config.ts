import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The Command Center reads Supabase over the network and renders live data;
  // nothing is statically exported.
  reactStrictMode: true,
  // Type checking stays ON (a type error fails the build — the real safety
  // net). Lint is run via `npm run lint` in CI rather than gating the Vercel
  // production build, so a style nit never blocks a deploy.
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
