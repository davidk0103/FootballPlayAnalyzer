import { expect, type Page } from '@playwright/test'

// The admin is created before the suite runs (CI: `python -m app.auth create-admin`).
export const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? 'admin@playbookiq.test'
export const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? 'e2e-admin-password'

export async function signIn(page: Page, email: string, password: string) {
  await page.goto(`/login?next=${encodeURIComponent('/')}`)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
}

/** Register a fresh, unique user through the UI and stay signed in. */
export async function registerNewUser(page: Page): Promise<string> {
  const email = `coach-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`
  await page.goto('/register')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('e2e-coach-password')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
  return email
}
