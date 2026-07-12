import type { ReactNode } from "react";
import { AppSidebar } from "./AppSidebar";
import { AppTopbar } from "./AppTopbar";

export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div 
      className="min-h-screen w-full flex bg-background relative"
      style={{
        backgroundImage: "url('/airplane_bg.jpg')",
        backgroundSize: "cover",
        backgroundPosition: "center",
        backgroundAttachment: "fixed",
      }}
    >
      <div className="absolute inset-0 bg-background/95 backdrop-blur-[2px]" />
      <div className="relative z-10 flex w-full">
        <AppSidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <AppTopbar />
          <main className="flex-1 overflow-y-auto">
            <div className="mx-auto w-full max-w-7xl px-6 py-6">{children}</div>
          </main>
        </div>
      </div>
    </div>
  );
}
