// @lovable.dev/vite-tanstack-config already includes the app's framework, CSS,
// path, SSR, and deployment plugins. Load it at runtime so Vite's config
// bundler does not try to parse the platform-specific Tailwind native binding.
const load = (specifier: string) =>
  new Function("specifier", "return import(specifier)")(specifier) as Promise<unknown>;

export default async (env: import("vite").ConfigEnv) => {
  const { defineConfig } = (await load(
    "@lovable.dev/vite-tanstack-config/dist/index.js",
  )) as typeof import("@lovable.dev/vite-tanstack-config");

  return defineConfig({
    tanstackStart: {
      // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
      // nitro/vite builds from this
      server: { entry: "server" },
    },
    vite: {
      test: {
        globals: true,
        environment: "jsdom",
        setupFiles: ["./src/test/setup.ts"],
        pool: "threads",
      },
    } as any,
  })(env);
};
