import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ACTIVE_POLL_MS } from '@/hooks/useJobs'
import { newIdempotencyKey } from '@/lib/format'
import { api, type ExportFormat, type Report, type ReportRequest } from '@/services/api'

function busy(report: Report | undefined): boolean {
  return (
    report !== undefined &&
    (report.status === 'pending' || report.exports.some((e) => e.status === 'pending'))
  )
}

export function useReports() {
  return useQuery({
    queryKey: ['reports', 'list'],
    queryFn: () => api.reports(),
    refetchInterval: (query) =>
      query.state.data?.items.some((r) => r.status === 'pending') ? ACTIVE_POLL_MS : false,
  })
}

export function useReport(id: string) {
  return useQuery({
    queryKey: ['reports', id],
    queryFn: () => api.report(id),
    refetchInterval: (query) => (busy(query.state.data) ? ACTIVE_POLL_MS : false),
  })
}

export function useCreateReport() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: ReportRequest) => api.createReport(body, newIdempotencyKey()),
    onSuccess: (report) => {
      client.setQueryData(['reports', report.id], report)
      void client.invalidateQueries({ queryKey: ['reports', 'list'] })
    },
  })
}

export function useDeleteReport() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.deleteReport(id),
    onSuccess: (_, id) => {
      client.removeQueries({ queryKey: ['reports', id] })
      void client.invalidateQueries({ queryKey: ['reports', 'list'] })
    },
  })
}

export function useCreateExport(id: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (format: ExportFormat) => api.createExport(id, format, newIdempotencyKey()),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['reports', id] })
    },
  })
}
