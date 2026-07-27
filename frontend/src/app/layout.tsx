import type { Metadata } from "next";
import { Toaster } from "sonner";
import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "ProxyChecker — Enterprise Proxy Infrastructure",
  description: "Enterprise-grade proxy scraping, validation, and delivery at scale",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
      </head>
      <body className="min-h-screen font-sans">
        <Providers>
          {children}
          <Toaster
            position="bottom-right"
            toastOptions={{
              style: { background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", color: "hsl(var(--foreground))" },
            }}
          />
        </Providers>
      </body>
    </html>
  );
}
