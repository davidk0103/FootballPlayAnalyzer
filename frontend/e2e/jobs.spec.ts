import { expect, test } from '@playwright/test'

// Requires a running Celery worker and the 2023 season already imported, so the job
// finishes quickly as a checksum no-op (`make up && make ingest SEASONS=2023`).
test('queue an import and watch it finish', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('link', { name: 'Jobs' }).click()
  await expect(page.getByRole('heading', { name: 'Import jobs' })).toBeVisible()

  await page.getByLabel('Season').fill('2023')
  await page.getByRole('button', { name: 'Queue import' }).click()
  await expect(page).toHaveURL(/\/jobs\?job=[0-9a-f-]{36}/)

  const jobId = new URL(page.url()).searchParams.get('job')
  const row = page.locator(`[data-job-id="${jobId}"]`)
  await expect(row.getByText('Succeeded')).toBeVisible({ timeout: 20_000 })
  await expect(row.getByText(/Already up to date|plays stored/)).toBeVisible()
  await expect(row.getByText('Attempt 1: Succeeded')).toBeVisible()
})
