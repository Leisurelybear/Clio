import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['clio/ui/static/src/__tests__/**/*.test.js'],
  },
});
