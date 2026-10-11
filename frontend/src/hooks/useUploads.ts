import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ACTIVE_POLL_MS } from '@/hooks/useJobs'
import { newIdempotencyKey } from '@/lib/format'
import { api, type UploadDetail } from '@/services/api'

export function useMyUploads(enabled = true) {
  return useQuery({
    queryKey: ['uploads', 'list'],
    queryFn: () => api.uploads(),
    enabled,
    refetchInterval: (query) =>
      query.state.data?.items.some((u) => u.status === 'processing') ? ACTIVE_POLL_MS : false,
  })
}

export function useUpload(id: string | null) {
  return useQuery({
    queryKey: ['uploads', id],
    queryFn: () => api.upload(id as string),
    enabled: id !== null,
    refetchInterval: (query) =>
      query.state.data?.status === 'processing' ? ACTIVE_POLL_MS : false,
  })
}

export function useUploadTeams(id: string | null, ready: boolean) {
  return useQuery({
    queryKey: ['uploads', id, 'teams'],
    queryFn: () => api.uploadTeams(id as string),
    enabled: id !== null && ready,
    staleTime: Infinity,
  })
}

export function useRejectedRows(id: string, page: number, enabled: boolean) {
  return useQuery({
    queryKey: ['uploads', id, 'rejected', page],
    queryFn: () => api.uploadRejected(id, page),
    enabled,
  })
}

export function useCreateUpload() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ file, name }: { file: File; name?: string }) => api.createUpload(file, name),
    onSuccess: (upload) => {
      client.setQueryData(['uploads', upload.id], upload)
      void client.invalidateQueries({ queryKey: ['uploads', 'list'] })
    },
  })
}

export function useValidateUpload(id: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (mapping: Record<string, string>) => api.validateUpload(id, mapping),
    onSuccess: (result) => {
      client.setQueryData<UploadDetail>(['uploads', id], (old) =>
        old ? { ...old, ...result.upload } : old,
      )
    },
  })
}

export function useProcessUpload(id: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.processUpload(id, newIdempotencyKey()),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['uploads'] })
    },
  })
}

export function useDeleteUpload() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.deleteUpload(id),
    onSuccess: (_, id) => {
      client.removeQueries({ queryKey: ['uploads', id] })
      void client.invalidateQueries({ queryKey: ['uploads', 'list'] })
    },
  })
}
