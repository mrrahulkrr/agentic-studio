import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Agentic Studio",
};

export default function ClientLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
