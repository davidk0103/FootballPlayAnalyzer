import { expect, test } from '@playwright/test'

// Requires an API with the 2023 season imported (`make ingest SEASONS=2023`).
test('pick two teams and see their metrics', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('navigation', { name: 'Main', exact: true }).getByRole('link', { name: 'Compare' }).click()
  await expect(page.getByText('Pick two teams to compare')).toBeVisible()

  await page.getByLabel('Season', { exact: true }).selectOption('2023')
  await page.getByLabel('Team A').selectOption('KC')
  await page.getByLabel('Team B').selectOption('DET')

  const metrics = page.getByRole('region', { name: 'Metrics' })
  await expect(metrics).toBeVisible()
  for (const side of ['a', 'b']) {
    await expect(page.getByTestId(`metric-epa_per_play-${side}`)).toHaveText(/^[+-]?\d\.\d{3}$/)
    await expect(page.getByTestId(`metric-success_rate-${side}`)).toHaveText(/^\d{1,3}\.\d%$/)
  }
  await expect(page.getByText(/\d[\d,]* plays · \d+ games?/).first()).toBeVisible()
  await expect(page).toHaveURL(/team_a=KC&team_b=DET&season=2023/)
})
