import path from "node:path";
import { defineConfig } from "vitest/config";

// The intelligence derivations are pure functions over Supabase row shapes, so
// they run in a plain node environment — no DOM or network needed.
export default defineConfig({
  resolve: {
    alias: { "@": path.resolve(process.cwd()) },
  },
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
});
