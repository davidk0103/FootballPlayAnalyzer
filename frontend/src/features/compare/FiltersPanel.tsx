import { zodResolver } from '@hookform/resolvers/zod'
import { ChevronDown, SlidersHorizontal } from 'lucide-react'
import { useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Toggle } from '@/components/ui/toggle'
import {
  activeFilterCount,
  DEFAULT_FILTERS,
  DISTANCE_LABELS,
  DISTANCES,
  DOWNS,
  FIELD_ZONE_LABELS,
  FIELD_ZONES,
  filtersSchema,
  type FilterValues,
  QUARTERS,
} from './filters'

function toggle(list: number[], value: number): number[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value].sort((x, y) => x - y)
}

const ordinal = (n: number) => ['1st', '2nd', '3rd', '4th'][n - 1] ?? `${n}th`

export function FiltersPanel({
  value,
  onApply,
}: {
  value: FilterValues
  onApply: (filters: FilterValues) => void
}) {
  const form = useForm<FilterValues>({
    resolver: zodResolver(filtersSchema),
    values: value,
  })
  const active = activeFilterCount(value)
  const [open, setOpen] = useState(false)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <SlidersHorizontal className="size-4" aria-hidden="true" /> Filters
          {active > 0 && <Badge variant="secondary">{active} active</Badge>}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="ml-auto lg:hidden"
            aria-expanded={open}
            aria-controls="filters-form"
            onClick={() => setOpen((o) => !o)}
          >
            {open ? 'Hide' : 'Show'}
            <ChevronDown aria-hidden="true" className={open ? 'rotate-180' : undefined} />
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent id="filters-form" className={open ? undefined : 'hidden lg:block'}>
        <form
          aria-label="Situational filters"
          className="flex flex-col gap-4"
          onSubmit={form.handleSubmit(onApply)}
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="side">Perspective</Label>
            <NativeSelect id="side" className="w-full" {...form.register('side')}>
              <NativeSelectOption value="offense">Offense (plays run)</NativeSelectOption>
              <NativeSelectOption value="defense">Defense (plays allowed)</NativeSelectOption>
            </NativeSelect>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="seasonType">Season phase</Label>
            <NativeSelect id="seasonType" className="w-full" {...form.register('seasonType')}>
              <NativeSelectOption value="">Regular season + playoffs</NativeSelectOption>
              <NativeSelectOption value="REG">Regular season</NativeSelectOption>
              <NativeSelectOption value="POST">Playoffs</NativeSelectOption>
            </NativeSelect>
          </div>

          <fieldset className="flex flex-col gap-1.5">
            <legend className="mb-1.5 text-sm font-medium">Down</legend>
            <Controller
              control={form.control}
              name="down"
              render={({ field }) => (
                <div className="flex flex-wrap gap-1.5">
                  {DOWNS.map((d) => (
                    <Toggle
                      key={d}
                      variant="outline"
                      size="sm"
                      aria-label={`${ordinal(d)} down`}
                      pressed={field.value.includes(d)}
                      onPressedChange={() => field.onChange(toggle(field.value, d))}
                    >
                      {ordinal(d)}
                    </Toggle>
                  ))}
                </div>
              )}
            />
          </fieldset>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="distance">Distance to go</Label>
            <NativeSelect id="distance" className="w-full" {...form.register('distance')}>
              <NativeSelectOption value="">Any distance</NativeSelectOption>
              {DISTANCES.map((d) => (
                <NativeSelectOption key={d} value={d}>
                  {DISTANCE_LABELS[d]}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="fieldZone">Field position</Label>
            <NativeSelect id="fieldZone" className="w-full" {...form.register('fieldZone')}>
              <NativeSelectOption value="">Anywhere</NativeSelectOption>
              {FIELD_ZONES.map((z) => (
                <NativeSelectOption key={z} value={z}>
                  {FIELD_ZONE_LABELS[z]}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>

          <fieldset className="flex flex-col gap-1.5">
            <legend className="mb-1.5 text-sm font-medium">Quarter</legend>
            <Controller
              control={form.control}
              name="qtr"
              render={({ field }) => (
                <div className="flex flex-wrap gap-1.5">
                  {QUARTERS.map((q) => (
                    <Toggle
                      key={q}
                      variant="outline"
                      size="sm"
                      aria-label={q === 5 ? 'Overtime' : `Quarter ${q}`}
                      pressed={field.value.includes(q)}
                      onPressedChange={() => field.onChange(toggle(field.value, q))}
                    >
                      {q === 5 ? 'OT' : `Q${q}`}
                    </Toggle>
                  ))}
                </div>
              )}
            />
          </fieldset>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="playType">Play type</Label>
            <NativeSelect id="playType" className="w-full" {...form.register('playType')}>
              <NativeSelectOption value="">Pass and run</NativeSelectOption>
              <NativeSelectOption value="pass">Pass (incl. sacks)</NativeSelectOption>
              <NativeSelectOption value="run">Run (incl. scrambles)</NativeSelectOption>
            </NativeSelect>
          </div>

          <div className="flex gap-2 pt-1">
            <Button type="submit" className="flex-1">
              Apply filters
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                form.reset(DEFAULT_FILTERS)
                onApply(DEFAULT_FILTERS)
              }}
            >
              Reset
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}
