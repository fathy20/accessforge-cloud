// @lovable.dev/vite-tanstack-config already includes the app's framework, CSS,
// path, SSR, and deployment plugins. Load it at runtime so Vite's config
// bundler does not try to parse the platform-specific Tailwind native binding.
const load = (specifier: string) =>
  new Function("specifier", "return import(specifier)")(specifier) as Promise<unknown>;

// The FastAPI backend the dev server proxies `/api` to. In production the
// same path is served by the reverse proxy in front of the static build, so
// the client never needs an absolute API origin (and CORS is not involved).
const DEV_API_ORIGIN = process.env.DEV_API_ORIGIN ?? "http://localhost:8000";

export default async (env: import("vite").ConfigEnv) => {
  const { defineConfig } = (await load(
    "@lovable.dev/vite-tanstack-config/dist/index.js",
  )) as typeof import("@lovable.dev/vite-tanstack-config");

  return defineConfig({
    // Static SPA. Every authenticated route was already `ssr: false`, so the
    // Node/nitro server only ever rendered the landing and auth pages; those
    // are prerendered to HTML at build time instead. The output in
    // `dist/client` is a plain static site for any CDN or nginx.
    nitro: false,
    tanstackStart: {
      // maskPath is the route whose render becomes `_shell.html`. Leaving it at
      // "/" would swallow the landing page into the shell; pointing it at an
      // already client-only route lets "/" prerender as a real index.html.
      spa: { enabled: true, maskPath: "/dashboard" },
      // Public pages become full HTML; every other static route path is also
      // emitted as a copy of the shell so deep links load on hosts without a
      // SPA fallback rule.
      prerender: { enabled: true, crawlLinks: false },
      pages: [{ path: "/" }, { path: "/auth" }, { path: "/reset-password" }],
    },
    vite: {
      server: {
        proxy: {
          "/api": { target: DEV_API_ORIGIN, changeOrigin: true },
        },
      },
      test: {
        globals: true,
        environment: "jsdom",
        setupFiles: ["./src/test/setup.ts"],
        pool: "threads",
      },
    } as any,
  })(env);
};
