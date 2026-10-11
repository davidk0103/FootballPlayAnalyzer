import { expect, test } from '@playwright/test'

// Runs against the real 2023 season (CI ingests it before the suite).

test('team overview ranks offense and defense against the league', async ({ page }) => {
  await page.goto('/overview?season=2023&team=DET')
  const offense = page.getByLabel('offense metrics')
  await expect(offense.getByLabel('EPA / play')).toContainText(/Rank \d+ of 32/)
  await expect(page.getByLabel('defense metrics')).toBeVisible()
  await expect(page.getByRole('img', { name: /DET EPA per play by game/ })).toBeVisible()
  await expect(page.getByText('How these are calculated')).toBeVisible()
})

test('situational explorer slices by situation and keeps filters in the URL', async ({ page }) => {
  await page.goto('/situational?season=2023&team=KC')
  const table = page.getByRole('table', { name: 'Situational breakdown' })
  await expect(table.getByRole('cell', { name: '1st down' })).toBeVisible()

  await page.getByLabel('Break down by').selectOption('qtr')
  await expect(table.getByRole('cell', { name: 'Q1', exact: true })).toBeVisible()
  await expect(page).toHaveURL(/group_by=qtr/)

  await page.getByRole('button', { name: '3rd down' }).click()
  await page.getByRole('button', { name: 'Apply filters' }).click()
  await expect(page).toHaveURL(/down=3/)
  await expect(table.getByRole('cell', { name: 'All situations' })).toBeVisible()
  await expect(page.getByRole('table', { name: 'Pass rate by down and distance' })).toBeVisible()

  await page.reload()
  await expect(page.getByRole('button', { name: '3rd down' })).toHaveAttribute('aria-pressed', 'true')
})

test('player explorer compares two players', async ({ page }) => {
  await page.goto('/players?season=2023')
  await page.getByLabel('Name').fill('Mahomes')
  await page.getByRole('button', { name: /Compare Patrick Mahomes/ }).click()
  await page.getByLabel('Name').fill('Goff')
  await page.getByRole('button', { name: /Compare Jared Goff/ }).click()

  const table = page.getByRole('table', { name: 'Player comparison' })
  await expect(table.getByRole('columnheader', { name: /Patrick Mahomes/ })).toBeVisible()
  await expect(table.getByRole('columnheader', { name: /Jared Goff/ })).toBeVisible()
  await expect(table.getByRole('cell', { name: 'Pass attempts' })).toBeVisible()
  await expect(page.getByText('Limitations')).toBeVisible()
})
