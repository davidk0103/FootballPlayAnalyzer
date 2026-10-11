import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { location, renderWithProviders } from '@/test/render'
import { COACH, server } from '@/test/server'
import { Route, Routes } from 'react-router-dom'
import { safeNext } from '@/lib/navigation'
import { AuthPage } from './AuthPage'

describe('AuthPage', () => {
  it('signs in with the CSRF header and goes to the requested page', async () => {
    let csrf: string | null = null
    server.use(
      http.post('*/api/v1/auth/login', ({ request }) => {
        csrf = request.headers.get('X-PlaybookIQ-CSRF')
        return HttpResponse.json(COACH)
      }),
    )
    renderWithProviders(
      <Routes>
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="*" element={<p>Reports</p>} />
      </Routes>,
      { route: '/login?next=%2Freports' },
    )
    await userEvent.type(await screen.findByLabelText('Email'), 'coach@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'correct-horse-battery')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(location.current).toBe('/reports'))
    expect(csrf).toBe('1')
  })

  it('shows the server error for bad credentials', async () => {
    server.use(
      http.post('*/api/v1/auth/login', () =>
        HttpResponse.json(
          { error: { code: 'invalid_credentials', message: 'Incorrect email or password', request_id: 'r' } },
          { status: 401 },
        ),
      ),
    )
    renderWithProviders(<AuthPage mode="login" />, { route: '/login' })
    await userEvent.type(await screen.findByLabelText('Email'), 'coach@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password')
  })

  it('validates registration input before calling the API', async () => {
    let called = false
    server.use(
      http.post('*/api/v1/auth/register', () => {
        called = true
        return HttpResponse.json(COACH, { status: 201 })
      }),
    )
    renderWithProviders(<AuthPage mode="register" />, { route: '/register' })
    await userEvent.type(await screen.findByLabelText('Email'), 'not-an-email')
    await userEvent.type(screen.getByLabelText('Password'), 'short')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByText('Enter a valid email address')).toBeInTheDocument()
    expect(screen.getByText('Use at least 10 characters')).toBeInTheDocument()
    expect(called).toBe(false)
  })

  it('only redirects to same-site paths', () => {
    expect(safeNext('/upload')).toBe('/upload')
    expect(safeNext('//evil.example')).toBe('/')
    expect(safeNext('https://evil.example')).toBe('/')
    expect(safeNext(null)).toBe('/')
  })
})
