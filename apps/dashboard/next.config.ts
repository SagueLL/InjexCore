import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["http://localhost:3000", "http://localhost:3001", "192.168.56.1"]
};

export default nextConfig;
