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
  themeColor: "#ffffff",
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
        <Nav />
        <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col px-4 py-6 pb-[calc(5rem+env(safe-area-inset-bottom))] sm:pb-6">
          {children}
        </main>
        <MobileNav />
      </body>
    </html>
  );
}
