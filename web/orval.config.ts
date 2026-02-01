import { defineConfig } from 'orval';

export default defineConfig({
  vartalaap: {
    input: {
      target: '../openapi.json',
    },
    output: {
      mode: 'tags-split',
      target: './src/api/endpoints',
      schemas: './src/api/model',
      client: 'react-query',
      httpClient: 'axios',
      clean: true,
      prettier: true,
      override: {
        mutator: {
          path: './src/api/mutator/custom-instance.ts',
          name: 'customInstance',
        },
        query: {
          useQuery: true,
          useMutation: true,
          useSuspenseQuery: true,
          signal: true,
        },
      },
    },
    // Note: prettier: true above handles formatting; no afterAllFilesWrite hook needed
  },
  // Note: MSW mock generation removed - client compatibility issues with Orval 7.x
  // For testing, use vitest with manual mocking instead
});
