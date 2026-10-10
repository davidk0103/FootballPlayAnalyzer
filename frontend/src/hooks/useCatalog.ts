import { useQuery } from '@tanstack/react-query'
import { api } from '@/services/api'

export function useTeams() {
  return useQuery({ queryKey: ['teams'], queryFn: api.teams, staleTime: Infinity })
}

export function useSeasons() {
  return useQuery({ queryKey: ['seasons'], queryFn: api.seasons, staleTime: 5 * 60_000 })
}
