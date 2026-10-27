import type { Metadata, Viewport } from "next";
import { Manrope } from "next/font/google";
import { Nav, MobileNav } from "@/components/nav";
import "./globals.css";
import { UnitPreferences } from "@/components/unit-preferences";
import { THEME_BOOT_SCRIPT, ThemeWatcher } from "@/components/theme-preference";

const manrope = Manrope({
  variable: "--font-manrope",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700", "800"],
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
      className={`${manrope.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col text-foreground">
        <ThemeWatcher />
        <UnitPreferences>
        {/* Tablets and desktops: one glass shell holds the nav and the page, as in the wireframes. */}
        <div className="app-shell mx-auto flex w-full max-w-[1320px] flex-1 flex-col sm:my-4 sm:w-[calc(100%-2rem)] sm:px-5 sm:pb-5 lg:px-7">
          {process.env.STRIDE_DEMO_SCENARIO && <div role="status" className="glass-tile mx-4 mt-3 rounded-full px-4 py-2 text-center text-xs sm:mx-0">Synthetic demo: {process.env.STRIDE_DEMO_SCENARIO} · Garmin and AI calls disabled · Your personal database is separate</div>}
          <Nav />
          <main className="flex w-full flex-1 flex-col px-4 pt-3 pb-[calc(6.5rem+env(safe-area-inset-bottom))] sm:px-0 sm:pt-5 sm:pb-2">
            {children}
          </main>
        </div>
        <MobileNav />
        </UnitPreferences>
      </body>
    </html>
  );
}
