import { Label } from '@/components/ui/label'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import type { Season } from '@/services/api'

export function SeasonSelect({
  seasons,
  value,
  onChange,
}: {
  seasons: Season[]
  value: number | null
  onChange: (season: number) => void
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor="season">Season</Label>
      <NativeSelect
        id="season"
        className="w-full"
        value={value === null ? '' : String(value)}
        onChange={(e) => onChange(Number(e.target.value))}
      >
        {value === null && <NativeSelectOption value="">Choose a season</NativeSelectOption>}
        {seasons.map((s) => (
          <NativeSelectOption key={s.season} value={String(s.season)}>
            {s.season}
          </NativeSelectOption>
        ))}
      </NativeSelect>
    </div>
  )
}
