import { QueryClient } from '@tanstack/react-query'

/**
 * Global TanStack Query client.
 *
 * Ownership rules:
 *  - Only mutation hooks (useFoo) call queryClient.invalidateQueries.
 *  - Pages MUST NOT import queryClient directly for invalidation.
 *  - queryClient may be imported in pages ONLY for reading (getQueryData).
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,           // 30 s — fresh enough for most lists
      gcTime: 5 * 60 * 1000,       // 5 min — keep inactive data in cache
      retry: (failureCount, error) => {
        // Errors thrown by apiClient are normalised to ApiError shape
        const status = (error as { status?: number }).status
        // Don't retry on auth / client errors
        if (status !== undefined && status >= 400 && status < 500) return false
        return failureCount < 2
      },
      refetchOnWindowFocus: true,
    },
    mutations: {
      // Mutations never retry — they have side effects
      retry: false,
    },
  },
})
