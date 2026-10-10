import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api, type ComparisonQuery } from '@/services/api'

export function useTeamComparison(query: ComparisonQuery | null) {
  return useQuery({
    queryKey: ['team-comparison', query],
    queryFn: () => api.teamComparison(query as ComparisonQuery),
    enabled: query !== null,
    placeholderData: keepPreviousData,
    staleTime: 5 * 60_000,
  })
}
