import { z } from 'zod'
import type { ReportRequest } from '@/services/api'
import type { Scope } from '@/features/analytics/scope'

const week = z.union([z.literal(''), z.coerce.number().int().min(1, 'Weeks run 1-22').max(22, 'Weeks run 1-22')])

export const reportFormSchema = z
  .object({
    title: z.string().max(120, 'Keep the title under 120 characters'),
    seasonType: z.enum(['', 'REG', 'POST']),
    weekMin: week,
    weekMax: week,
    opponent: z
      .string()
      .trim()
      .regex(/^([A-Za-z]{2,3})?$/, 'Use a team abbreviation such as KC'),
  })
  .refine((v) => v.weekMin === '' || v.weekMax === '' || v.weekMin <= v.weekMax, {
    message: 'The first week must come before the last week',
    path: ['weekMax'],
  })

export type ReportFormInput = z.input<typeof reportFormSchema>
export type ReportFormValues = z.output<typeof reportFormSchema>

export const DEFAULT_REPORT_FORM: ReportFormInput = {
  title: '',
  seasonType: '',
  weekMin: '',
  weekMax: '',
  opponent: '',
}

export function toReportRequest(scope: Scope, v: ReportFormValues): ReportRequest {
  return {
    title: v.title.trim() || null,
    team: scope.team,
    season: scope.datasetId ? null : scope.season,
    dataset_id: scope.datasetId,
    season_type: v.seasonType || null,
    week_min: v.weekMin === '' ? null : v.weekMin,
    week_max: v.weekMax === '' ? null : v.weekMax,
    opponent: v.opponent ? v.opponent.toUpperCase() : null,
    explosive_run_yards: 10,
    explosive_pass_yards: 20,
    idempotency_key: null,
  }
}
