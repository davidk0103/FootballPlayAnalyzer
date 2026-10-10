import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { type ReactElement, useEffect } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'

export const location = { current: '' }

function LocationSpy() {
  const loc = useLocation()
  useEffect(() => {
    location.current = `${loc.pathname}${loc.search}`
  }, [loc])
  return null
}

export function renderWithProviders(ui: ReactElement, { route = '/' }: { route?: string } = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        {ui}
        <LocationSpy />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}
