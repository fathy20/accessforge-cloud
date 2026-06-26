import type { ReactNode } from "react";
import { AppSidebar } from "./AppSidebar";
import { AppTopbar } from "./AppTopbar";

export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen w-full bg-background text-foreground flex">
      <AppSidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <AppTopbar />
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-7xl px-6 py-6">{children}</div>
        </main>
      </div>
    </div>
  );
}
