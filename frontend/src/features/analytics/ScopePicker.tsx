import { useEffect } from 'react'
import { Label } from '@/components/ui/label'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Skeleton } from '@/components/ui/skeleton'
import { useCurrentUser } from '@/hooks/useAuth'
import { useSeasons, useTeams } from '@/hooks/useCatalog'
import { useMyUploads, useUploadTeams } from '@/hooks/useUploads'
import type { Scope } from './scope'

const PUBLIC = 'public'

/**
 * Data source (public nflverse season or one of your processed uploads), season, and team.
 * Uploads only appear when signed in; their teams come from the uploaded rows.
 */
export function ScopePicker({
  scope,
  onChange,
  teamOptional = false,
}: {
  scope: Scope
  onChange: (scope: Scope) => void
  teamOptional?: boolean
}) {
  const me = useCurrentUser()
  const signedIn = Boolean(me.data)
  const seasons = useSeasons()
  const teams = useTeams()
  const uploads = useMyUploads(signedIn)
  const ready = (uploads.data?.items ?? []).filter((u) => u.status === 'ready')
  const uploadTeams = useUploadTeams(scope.datasetId, scope.datasetId !== null)

  const latest = seasons.data?.[0]?.season ?? null
  useEffect(() => {
    if (!scope.datasetId && scope.season === null && latest !== null) {
      onChange({ ...scope, season: latest })
    }
  }, [scope, latest, onChange])

  if (seasons.isPending || teams.isPending) {
    return (
      <div className="grid gap-4 sm:grid-cols-3" aria-busy="true" aria-label="Loading filters">
        <Skeleton className="h-14" />
        <Skeleton className="h-14" />
        <Skeleton className="h-14" />
      </div>
    )
  }

  const teamOptions = scope.datasetId
    ? (uploadTeams.data ?? []).map((t) => ({ value: t.abbreviation, label: t.abbreviation }))
    : (teams.data ?? []).map((t) => ({ value: t.abbreviation, label: `${t.name} (${t.abbreviation})` }))

  return (
    <div className="grid items-end gap-4 sm:grid-cols-[minmax(0,1.3fr)_minmax(0,0.7fr)_minmax(0,1.3fr)]">
      <div className="flex min-w-0 flex-col gap-1.5">
        <Label htmlFor="scope-source">Data</Label>
        <NativeSelect
          id="scope-source"
          className="w-full"
          value={scope.datasetId ?? PUBLIC}
          onChange={(e) => {
            const value = e.target.value
            onChange({ ...scope, datasetId: value === PUBLIC ? null : value, team: '' })
          }}
        >
          <NativeSelectOption value={PUBLIC}>Public NFL data (nflverse)</NativeSelectOption>
          {ready.map((u) => (
            <NativeSelectOption key={u.id} value={u.id}>
              My upload: {u.name}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </div>
      <div className="flex min-w-0 flex-col gap-1.5">
        <Label htmlFor="scope-season">Season</Label>
        <NativeSelect
          id="scope-season"
          className="w-full"
          disabled={scope.datasetId !== null}
          value={scope.datasetId ? '' : scope.season === null ? '' : String(scope.season)}
          onChange={(e) => onChange({ ...scope, season: Number(e.target.value) })}
        >
          {scope.datasetId && <NativeSelectOption value="">All in upload</NativeSelectOption>}
          {(seasons.data ?? []).map((s) => (
            <NativeSelectOption key={s.season} value={String(s.season)}>
              {s.season}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </div>
      <div className="flex min-w-0 flex-col gap-1.5">
        <Label htmlFor="scope-team">Team</Label>
        <NativeSelect
          id="scope-team"
          className="w-full"
          value={scope.team}
          onChange={(e) => onChange({ ...scope, team: e.target.value })}
        >
          <NativeSelectOption value="">
            {teamOptional ? 'Whole league' : 'Choose a team'}
          </NativeSelectOption>
          {teamOptions.map((t) => (
            <NativeSelectOption key={t.value} value={t.value}>
              {t.label}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </div>
    </div>
  )
}
