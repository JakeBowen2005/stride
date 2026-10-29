import { Nav, MobileNav } from "@/components/nav";
import { UnitPreferences } from "@/components/unit-preferences";

// The signed-in app (and its sign-in/legal pages): one glass shell holds the nav and the page.
// The public landing page at /welcome lives outside this group and draws its own chrome.
export default function AppLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <UnitPreferences>
      {/* Tablets and desktops: one glass shell holds the nav and the page, as in the wireframes. */}
      <div className="app-shell mx-auto flex w-full max-w-[1320px] flex-1 flex-col sm:my-4 sm:w-[calc(100%-2rem)] sm:px-5 sm:pb-5 lg:px-7">
        {process.env.STRIDE_DEMO_SCENARIO && <div role="status" className="glass-tile mx-4 mt-3 rounded-full px-4 py-2 text-center text-xs sm:mx-0">Synthetic demo: {process.env.STRIDE_DEMO_SCENARIO} · Garmin disabled · AI {process.env.STRIDE_DEMO_AI ? 'on' : 'off'} · Your personal database is separate</div>}
        <Nav />
        <main className="flex w-full flex-1 flex-col px-4 pt-3 pb-[calc(6.5rem+env(safe-area-inset-bottom))] sm:px-0 sm:pt-5 sm:pb-2">
          {children}
        </main>
      </div>
      <MobileNav />
    </UnitPreferences>
  );
}
