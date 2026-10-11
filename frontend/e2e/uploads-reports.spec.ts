import path from 'node:path'
import { expect, test } from '@playwright/test'
import { registerNewUser } from './helpers.ts'

// Needs the API, a Celery worker and the real 2023 season (see jobs.spec.ts).
const CSV = path.join(import.meta.dirname, 'fixtures', 'week1-charting.csv')

test('upload a CSV, map it, process it, then analyze and report on it', async ({ page }) => {
  await registerNewUser(page)
  await page.goto('/uploads')
  await expect(page.getByText('No uploads yet')).toBeVisible()

  await page.getByTestId('file-input').setInputFiles(CSV)
  await page.getByLabel('Name').fill('Week 1 charting')
  await page.getByRole('button', { name: 'Upload and check' }).click()
  await expect(page).toHaveURL(/\/uploads\/[0-9a-f-]{36}$/)

  await expect(page.getByLabel('Column for Offense')).toHaveValue('Off')
  await page.getByLabel('Column for Yards from end zone').selectOption('Field Pos')
  await page.getByRole('button', { name: 'Check mapping' }).click()
  const result = page.getByTestId('validation-result')
  await expect(result).toContainText('258 accepted, 2 would be set aside')
  await expect(result).toContainText("Down must be a whole number from 1 to 4 (got '5')")

  await page.getByRole('button', { name: 'Process all rows' }).click()
  await expect(page.getByText('258 plays stored, 2 set aside')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByRole('table', { name: 'Teams in this upload' })).toContainText('DET')
  await expect(page.getByRole('table', { name: 'Rejected rows' })).toContainText('Offense is blank')

  await page.getByRole('link', { name: /Explore situations/ }).click()
  await page.getByLabel('Team', { exact: true }).selectOption('DET')
  const table = page.getByRole('table', { name: 'Situational breakdown' })
  await expect(table.getByRole('cell', { name: 'All situations' })).toBeVisible()
  await expect(page.getByText(/Your upload “Week 1 charting”/)).toBeVisible()

  await page.goto('/reports?new=1')
  await page.getByLabel('Data', { exact: true }).selectOption({ label: 'My upload: Week 1 charting' })
  await page.getByLabel('Team', { exact: true }).selectOption('DET')
  await page.getByRole('button', { name: 'Generate report' }).click()
  await expect(page).toHaveURL(/\/reports\/[0-9a-f-]{36}$/)
  await expect(page.getByRole('table', { name: 'offense metrics' })).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText('League values and ranks are computed across the teams in your uploaded dataset.')).toBeVisible()
})

test('generate a saved scouting report and export it', async ({ page }) => {
  await registerNewUser(page)
  await page.goto('/reports?new=1&season=2023&team=DET')
  await page.getByLabel('Title (optional)').fill('Lions 2023 scout')
  await page.getByRole('button', { name: 'Generate report' }).click()

  await expect(page.getByRole('heading', { name: /Lions 2023 scout/ })).toBeVisible()
  await expect(page.getByRole('table', { name: 'offense metrics' })).toContainText(/\d+ \/ 32/, { timeout: 30_000 })
  await expect(page.getByRole('table', { name: 'Red zone' })).toBeVisible()

  await page.getByRole('button', { name: 'Export CSV' }).click()
  const download = page.getByRole('link', { name: /Download/ })
  await expect(download).toBeVisible({ timeout: 30_000 })
  const [file] = await Promise.all([page.waitForEvent('download'), download.click()])
  expect(file.suggestedFilename()).toBe('playbookiq-lions-2023-scout.csv')

  await page.goto('/reports')
  await expect(page.getByRole('link', { name: 'Lions 2023 scout' })).toBeVisible()
})
