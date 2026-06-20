/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Emit a minimal self-contained server bundle (.next/standalone) so the
  // production Docker image ships only the files it needs to run.
  output: "standalone",
};

export default nextConfig;
