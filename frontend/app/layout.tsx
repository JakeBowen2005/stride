import type { Metadata, Viewport } from "next";
import { Instrument_Serif, Manrope } from "next/font/google";
import { GeistMono } from "geist/font/mono";
import "./globals.css";
import { THEME_BOOT_SCRIPT, ThemeWatcher } from "@/components/theme-preference";

const manrope = Manrope({
  variable: "--font-manrope",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700", "800"],
});

// Landing page only: an editorial serif for the human voice, Geist Mono for the numbers.
const instrumentSerif = Instrument_Serif({
  variable: "--font-instrument-serif",
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: "Stride",
  description: "AI-powered running coach",
  applicationName: "Stride",
  // "Add to Home Screen" on iPhone opens full-screen like a native app
  appleWebApp: { capable: true, title: "Stride", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fbe6da" },
    { media: "(prefers-color-scheme: dark)", color: "#3a3f5c" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      // The boot script sets .dark before hydration
      suppressHydrationWarning
      className={`${manrope.variable} ${instrumentSerif.variable} ${GeistMono.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col text-foreground">
        <ThemeWatcher />
        {children}
      </body>
    </html>
  );
}
