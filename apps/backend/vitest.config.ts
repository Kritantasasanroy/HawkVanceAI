import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // Every suite here talks to one real Postgres schema and truncates between tests. Running
    // files in parallel means one suite wipes another's fixtures mid-run. Real integration tests
    // against a shared database are worth more than the parallelism they cost.
    fileParallelism: false,
    hookTimeout: 30_000,
    testTimeout: 30_000,
  },
});
