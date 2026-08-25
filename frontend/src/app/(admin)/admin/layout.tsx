import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Agentic Studio — Admin",
};

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
