import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api, type AnalyticsQuery, type GroupBy } from '@/services/api'

/** Public data needs a season; an upload does not. */
export function hasSource(q: AnalyticsQuery): boolean {
  return Boolean(q.datasetId) || (q.season !== null && q.season !== undefined)
}

export function useSituational(q: AnalyticsQuery & { team: string | null; groupBy: GroupBy }) {
  return useQuery({
    queryKey: ['situational', q],
    queryFn: () => api.situational(q),
    enabled: hasSource(q),
    placeholderData: keepPreviousData,
  })
}

export function useEfficiency(q: AnalyticsQuery & { team: string }) {
  return useQuery({
    queryKey: ['efficiency', q],
    queryFn: () => api.efficiency(q),
    enabled: hasSource(q) && Boolean(q.team),
    placeholderData: keepPreviousData,
  })
}

export function useTrends(q: AnalyticsQuery & { team: string }) {
  return useQuery({
    queryKey: ['trends', q],
    queryFn: () => api.trends(q),
    enabled: hasSource(q) && Boolean(q.team),
    placeholderData: keepPreviousData,
  })
}

export function useTendencies(q: AnalyticsQuery & { team: string }) {
  return useQuery({
    queryKey: ['tendencies', q],
    queryFn: () => api.tendencies(q),
    enabled: hasSource(q) && Boolean(q.team),
    placeholderData: keepPreviousData,
  })
}

export function usePlayerSearch(search: string, season: number | null, position: string) {
  const term = search.trim()
  return useQuery({
    queryKey: ['players', 'search', term, season, position],
    queryFn: () =>
      api.players({ search: term || undefined, season, position: position || undefined }),
    enabled: term.length >= 2 || season !== null,
    placeholderData: keepPreviousData,
  })
}

export function usePlayerStats(id: string | null, q: AnalyticsQuery) {
  return useQuery({
    queryKey: ['players', 'stats', id, q],
    queryFn: () => api.playerStats(id as string, q),
    enabled: id !== null,
  })
}
