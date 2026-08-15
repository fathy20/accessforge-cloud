import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useIsMobile } from "@/hooks/use-mobile";
import { useI18n } from "@/lib/i18n";
import { RedSeaCopilot, createWingmanTransport } from "@/components/copilot";
import { AppSidebar } from "./AppSidebar";
import { AppTopbar } from "./AppTopbar";

export function AppLayout({ children }: { children: ReactNode }) {
  const { dir, t } = useI18n();
  const isMobile = useIsMobile();
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  // Backed by LEON's own Wingman chat via POST /api/copilot/ask.
  const copilotTransport = useMemo(
    () =>
      createWingmanTransport({
        localContext: () =>
          typeof window === "undefined" ? undefined : window.location.pathname,
      }),
    [],
  );

  useEffect(() => {
    if (!isMobile) setMobileNavigationOpen(false);
  }, [isMobile]);

  return (
    // h-screen + overflow-hidden makes the shell exactly one viewport tall, so
    // the only scrollable region is <main>. That keeps the sidebar and topbar
    // in place without position:fixed, which would need width/offset mirroring
    // and break when the sidebar collapses or the direction flips to RTL.
    <div className="h-screen w-full overflow-hidden bg-background text-foreground" dir={dir}>
      <a
        href="#main-content"
        className="sr-only focus:fixed focus:start-page-gutter focus:top-3 focus:z-shell-skip-link focus:not-sr-only focus:rounded-md focus:border focus:border-interactive-focus focus:bg-surface-overlay focus:px-4 focus:py-2 focus:text-label focus:text-fg-primary"
      >
        {t("shell.skip_to_main")}
      </a>

      <div className="flex h-full w-full min-h-0">
        <AppSidebar
          isMobile={isMobile}
          mobileOpen={mobileNavigationOpen}
          onMobileOpenChange={setMobileNavigationOpen}
        />
        {/* min-h-0 lets this column shrink so its <main> child can scroll;
            without it a flex item defaults to min-height:auto and grows
            instead, pushing the topbar off screen. */}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <AppTopbar onOpenNavigation={() => setMobileNavigationOpen(true)} />
          <main id="main-content" tabIndex={-1} className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto w-full max-w-shell px-page-gutter py-section-rhythm">
              {children}
            </div>
          </main>
        </div>
      </div>

      <RedSeaCopilot transport={copilotTransport} />
    </div>
  );
}
