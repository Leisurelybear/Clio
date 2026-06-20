import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['vlog_tool/ui/static/src/__tests__/**/*.test.js'],
  },
});
