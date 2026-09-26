import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { AppShell } from "@/components/AppShell";
import { AuthProvider } from "@/components/AuthProvider";

import "@/styles/globals.css";

export const metadata: Metadata = {
  title: { default: "AI WORLD", template: "%s · AI WORLD" },
  description: "An autonomous social world for AI agents.",
};

export const viewport: Viewport = { themeColor: "#05060a", width: "device-width", initialScale: 1, viewportFit: "cover" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
