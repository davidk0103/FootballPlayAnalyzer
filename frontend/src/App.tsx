import { lazy, Suspense } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { EmptyState } from '@/components/StateViews'
import { ThemeToggle } from '@/components/ThemeToggle'
import { cn } from '@/lib/utils'
import { Skeleton } from '@/components/ui/skeleton'
import { LandingPage } from '@/pages/LandingPage'

const ComparePage = lazy(() =>
  import('@/pages/ComparePage').then((m) => ({ default: m.ComparePage })),
)

const navClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'rounded-md px-3 py-1.5 text-sm transition-colors hover:bg-muted',
    isActive ? 'font-medium text-foreground' : 'text-muted-foreground',
  )

export function App() {
  return (
    <div className="flex min-h-svh flex-col">
      <header className="border-b">
        <div className="mx-auto flex h-14 w-full max-w-7xl items-center gap-4 px-4 sm:px-6">
          <NavLink to="/" className="flex items-center gap-2 font-semibold tracking-tight">
            <span className="grid size-7 place-items-center rounded-md bg-primary text-xs text-primary-foreground">
              IQ
            </span>
            PlaybookIQ
          </NavLink>
          <nav className="flex items-center gap-1" aria-label="Main">
            <NavLink to="/compare" className={navClass}>
              Compare
            </NavLink>
          </nav>
          <div className="ml-auto">
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6">
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route
            path="/compare"
            element={
              <Suspense fallback={<Skeleton className="h-96" aria-label="Loading page" />}>
                <ComparePage />
              </Suspense>
            }
          />
          <Route path="*" element={<EmptyState title="Page not found">Try the Compare page.</EmptyState>} />
        </Routes>
      </main>

      <footer className="border-t">
        <div className="mx-auto w-full max-w-7xl px-4 py-4 text-xs text-muted-foreground sm:px-6">
          Play-by-play data courtesy of the{' '}
          <a className="underline" href="https://github.com/nflverse/nflverse-data" target="_blank" rel="noreferrer">
            nflverse project
          </a>{' '}
          (nflfastR / nflreadr). Non-commercial, educational use. Not affiliated with the NFL.
        </div>
      </footer>
    </div>
  )
}
