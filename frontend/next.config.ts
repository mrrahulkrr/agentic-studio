import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // No turbopack.root hack needed: all source lives under this directory.
  // No cross-package path resolution required.
};

export default nextConfig;
