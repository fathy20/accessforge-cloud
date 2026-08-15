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
    <div className="min-h-screen w-full bg-background text-foreground" dir={dir}>
      <a
        href="#main-content"
        className="sr-only focus:fixed focus:start-page-gutter focus:top-3 focus:z-shell-skip-link focus:not-sr-only focus:rounded-md focus:border focus:border-interactive-focus focus:bg-surface-overlay focus:px-4 focus:py-2 focus:text-label focus:text-fg-primary"
      >
        {t("shell.skip_to_main")}
      </a>

      <div className="flex min-h-screen w-full">
        <AppSidebar
          isMobile={isMobile}
          mobileOpen={mobileNavigationOpen}
          onMobileOpenChange={setMobileNavigationOpen}
        />
        <div className="flex min-w-0 flex-1 flex-col">
          <AppTopbar onOpenNavigation={() => setMobileNavigationOpen(true)} />
          <main id="main-content" tabIndex={-1} className="flex-1 overflow-y-auto">
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
