"use client";

import { AuthProvider } from "@/lib/auth";
import { ThemeProvider } from "@/lib/theme";
import { ServiceWorker } from "@/components/layout/ServiceWorker";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <AuthProvider>
        <ServiceWorker />
        {children}
      </AuthProvider>
    </ThemeProvider>
  );
}
