import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Nav, MobileNav } from "@/components/nav";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
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
  themeColor: "#1f1f1f",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-background text-foreground">
        {process.env.STRIDE_DEMO_SCENARIO && <div role="status" className="bg-primary px-4 py-2 lg:pl-[200px] text-center text-xs text-primary-foreground">Synthetic demo: {process.env.STRIDE_DEMO_SCENARIO} · Garmin and AI calls disabled · Your personal database is separate</div>}
        <Nav />
        <div className="flex flex-1 flex-col lg:pl-[184px]">
          <main className="mx-auto flex w-full max-w-[1280px] flex-1 flex-col px-4 py-5 pb-[calc(5rem+env(safe-area-inset-bottom))] sm:pb-6">
            {children}
          </main>
        </div>
        <MobileNav />
      </body>
    </html>
  );
}
