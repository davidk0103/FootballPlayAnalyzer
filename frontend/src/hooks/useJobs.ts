import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api, isActiveJob, type JobStatus } from '@/services/api'

/** Poll fast while anything is in flight, slowly otherwise (another tab may queue work). */
export const ACTIVE_POLL_MS = 1500
export const IDLE_POLL_MS = 10_000

export function useJobs(status: JobStatus | null) {
  return useQuery({
    queryKey: ['jobs', 'list', status],
    queryFn: () =>
      api.jobs({ status: status ?? undefined, taskType: 'import_season', pageSize: 50 }),
    placeholderData: keepPreviousData,
    refetchInterval: (query) =>
      query.state.data?.items.some(isActiveJob) ? ACTIVE_POLL_MS : IDLE_POLL_MS,
  })
}

export function useJob(id: string | null) {
  return useQuery({
    queryKey: ['jobs', id],
    queryFn: () => api.job(id as string),
    enabled: id !== null,
    refetchInterval: (query) =>
      query.state.data && isActiveJob(query.state.data) ? ACTIVE_POLL_MS : false,
  })
}

export function useCancelJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.cancelJob(id),
    onSuccess: (job) => {
      queryClient.setQueryData(['jobs', job.id], job)
      void queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}

export function useCacheStats() {
  return useQuery({
    queryKey: ['cache-stats'],
    queryFn: api.cacheStats,
    refetchInterval: IDLE_POLL_MS,
  })
}

/** A clock for live durations and countdowns: every second while busy, slowly otherwise. */
export function useNow(busy: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), busy ? 1000 : 30_000)
    return () => window.clearInterval(id)
  }, [busy])
  return now
}
