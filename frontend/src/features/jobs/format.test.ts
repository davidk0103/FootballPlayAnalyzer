import { describe, expect, it } from 'vitest'
import type { Job } from '@/services/api'
import succeeded from '@/test/fixtures/job-succeeded-2024.json'
import { formatDuration, formatRelative, isJobStatus, jobDuration, jobSummary } from './format'

const base = succeeded as Job
const NOW = Date.parse('2026-10-10T23:00:00Z')

describe('formatDuration', () => {
  it.each([
    [-1, '—'],
    [400, '<1s'],
    [8_250, '8s'],
    [60_000, '1m'],
    [95_000, '1m 35s'],
    [3_780_000, '1h 3m'],
  ])('%i ms -> %s', (ms, text) => {
    expect(formatDuration(ms)).toBe(text)
  })
})

describe('job formatting', () => {
  it('summarizes a real succeeded import', () => {
    expect(jobSummary(base, NOW)).toBe('43,110 plays stored')
    expect(jobDuration(base, NOW)).toBe('8s')
  })

  it('explains each lifecycle state', () => {
    const at = (status: Job['status'], extra: Partial<Job> = {}) =>
      jobSummary({ ...base, status, ...extra }, NOW)
    expect(at('queued')).toBe('Waiting for a worker')
    expect(at('running', { attempt_count: 2 })).toBe('Importing, attempt 2 of 4')
    expect(
      at('retrying', { attempt_count: 1, next_retry_at: new Date(NOW + 12_000).toISOString() }),
    ).toBe('Retrying in 12s after a temporary error (attempt 1 of 4)')
    expect(at('cancel_requested')).toMatch(/rolled back/)
    expect(at('cancelled')).toBe('Cancelled. No data was changed')
    expect(at('failed', { error: 'gave up after 4 attempts: timeout' })).toBe(
      'gave up after 4 attempts: timeout',
    )
    expect(at('succeeded', { result: { status: 'skipped_duplicate' } })).toMatch(/Already up to date/)
    expect(at('succeeded', { result: { status: 'imported', stored: 10, rejected: 1200 } })).toBe(
      '10 plays stored, 1,200 rows quarantined',
    )
  })

  it('formats relative times and validates statuses', () => {
    expect(formatRelative(new Date(NOW - 2_000).toISOString(), NOW)).toBe('just now')
    expect(formatRelative(new Date(NOW - 90_000).toISOString(), NOW)).toBe('1m ago')
    expect(formatRelative(new Date(NOW - 7_200_000).toISOString(), NOW)).toBe('2h ago')
    expect(isJobStatus('running')).toBe(true)
    expect(isJobStatus('bogus')).toBe(false)
    expect(isJobStatus(null)).toBe(false)
  })
})
