import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError, type Credentials, type User } from '@/services/api'

export const ME_KEY = ['auth', 'me'] as const

/** The signed-in user, `null` when signed out. 401 is an answer here, not an error. */
export function useCurrentUser() {
  return useQuery<User | null>({
    queryKey: ME_KEY,
    queryFn: async () => {
      try {
        return await api.me()
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null
        throw error
      }
    },
    staleTime: 5 * 60_000,
  })
}

export function useAuthMutation(mode: 'login' | 'register') {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: Credentials) => (mode === 'login' ? api.login(body) : api.register(body)),
    onSuccess: (user) => {
      // Cached private data belongs to whoever was signed in before.
      client.removeQueries({ predicate: (q) => q.queryKey[0] !== 'auth' })
      client.setQueryData(ME_KEY, user)
    },
  })
}

export function useLogout() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (everywhere: boolean) => (everywhere ? api.logoutAll() : api.logout()),
    onSettled: () => {
      client.removeQueries({ predicate: (q) => q.queryKey[0] !== 'auth' })
      client.setQueryData(ME_KEY, null)
    },
  })
}
