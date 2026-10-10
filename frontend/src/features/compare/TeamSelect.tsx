import { Label } from '@/components/ui/label'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import type { Team } from '@/services/api'

export function TeamSelect({
  id,
  label,
  teams,
  value,
  disabledValue,
  onChange,
  accent,
}: {
  id: string
  label: string
  teams: Team[]
  value: string
  disabledValue?: string
  onChange: (abbreviation: string) => void
  accent: 'a' | 'b'
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id} className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className={accent === 'a' ? 'size-2.5 rounded-full bg-team-a' : 'size-2.5 rounded-full bg-team-b'}
        />
        {label}
      </Label>
      <NativeSelect
        id={id}
        className="w-full"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <NativeSelectOption value="">Choose a team</NativeSelectOption>
        {teams.map((team) => (
          <NativeSelectOption
            key={team.id}
            value={team.abbreviation}
            disabled={team.abbreviation === disabledValue}
          >
            {team.name} ({team.abbreviation})
          </NativeSelectOption>
        ))}
      </NativeSelect>
    </div>
  )
}
