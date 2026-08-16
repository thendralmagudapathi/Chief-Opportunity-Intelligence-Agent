import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // Produces .next/standalone, which the runtime Docker stage copies.
  output: "standalone",
  env: {
    NEXT_PUBLIC_API_BASE_URL:
      process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
  },
};

export default config;
