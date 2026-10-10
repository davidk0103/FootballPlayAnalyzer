import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Play } from 'lucide-react'
import { useRef } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { z } from 'zod'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api, ApiError } from '@/services/api'

export const FIRST_SEASON = 1999
export const LATEST_SEASON = 2025

const schema = z.object({
  season: z
    .number({ error: 'Enter a season year' })
    .int()
    .min(FIRST_SEASON, `nflverse play-by-play starts in ${FIRST_SEASON}`)
    .max(LATEST_SEASON, `Latest available season is ${LATEST_SEASON}`),
  force: z.boolean(),
})
type FormValues = z.infer<typeof schema>

function existingJobId(error: ApiError): string | null {
  const details = error.details
  if (details && typeof details === 'object' && 'existing_job_id' in details) {
    const id = (details as { existing_job_id: unknown }).existing_job_id
    return typeof id === 'string' ? id : null
  }
  return null
}

export function ImportJobForm({ onShowJob }: { onShowJob: (jobId: string) => void }) {
  const queryClient = useQueryClient()
  // One key per submission intent: automatic retries of the same request reuse it, so a
  // timeout followed by a retry can never create a second job.
  const keyRef = useRef<string | null>(null)
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { season: 2024, force: false },
  })

  const mutation = useMutation({
    mutationFn: (values: FormValues) => {
      keyRef.current ??= crypto.randomUUID()
      return api.submitImport({ ...values, idempotencyKey: keyRef.current })
    },
    retry: (count, error) => error instanceof ApiError && error.status === 0 && count < 2,
    onSuccess: (job) => {
      keyRef.current = null
      void queryClient.invalidateQueries({ queryKey: ['jobs'] })
      onShowJob(job.id)
    },
    onError: () => {
      keyRef.current = null
    },
  })

  const error = mutation.error instanceof ApiError ? mutation.error : null
  const duplicateOf = error?.code === 'duplicate_job' ? existingJobId(error) : null

  return (
    <form
      noValidate
      onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
      className="flex flex-col gap-4"
      aria-label="Start an import"
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="import-season">Season</Label>
        <Input
          id="import-season"
          type="number"
          inputMode="numeric"
          min={FIRST_SEASON}
          max={LATEST_SEASON}
          aria-invalid={form.formState.errors.season ? true : undefined}
          aria-describedby="import-season-help"
          {...form.register('season', { valueAsNumber: true })}
        />
        <p id="import-season-help" className="text-xs text-muted-foreground">
          {form.formState.errors.season?.message ??
            `Any season from ${FIRST_SEASON} to ${LATEST_SEASON}. The file is downloaded once and cached.`}
        </p>
      </div>

      <Controller
        control={form.control}
        name="force"
        render={({ field }) => (
          <div className="flex items-start gap-2">
            <Checkbox
              id="import-force"
              checked={field.value}
              onCheckedChange={(checked) => field.onChange(checked === true)}
              className="mt-0.5"
            />
            <div className="flex flex-col gap-0.5">
              <Label htmlFor="import-force">Re-import even if unchanged</Label>
              <span className="text-xs text-muted-foreground">
                Normally an identical file (same checksum) is skipped.
              </span>
            </div>
          </div>
        )}
      />

      <Button type="submit" disabled={mutation.isPending} className="self-start">
        <Play aria-hidden="true" />
        {mutation.isPending ? 'Queuing…' : 'Queue import'}
      </Button>

      {mutation.isError && (
        <Alert variant="destructive" role="alert">
          <AlertTitle>
            {duplicateOf ? 'This season is already being imported' : 'Could not queue the import'}
          </AlertTitle>
          <AlertDescription>
            {duplicateOf ? (
              <span>
                Only one import per season runs at a time.{' '}
                <button
                  type="button"
                  className="underline underline-offset-2"
                  onClick={() => onShowJob(duplicateOf)}
                >
                  View the running job
                </button>
              </span>
            ) : (
              (mutation.error?.message ?? 'Unexpected error')
            )}
          </AlertDescription>
        </Alert>
      )}
    </form>
  )
}
