import { lazy, Suspense, type ComponentType, type ReactNode } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { RequireAuth } from '@/components/RequireAuth'
import { EmptyState } from '@/components/StateViews'
import { ThemeToggle } from '@/components/ThemeToggle'
import { UserMenu } from '@/components/UserMenu'
import { cn } from '@/lib/utils'
import { Skeleton } from '@/components/ui/skeleton'
import { AuthPage } from '@/pages/AuthPage'
import { LandingPage } from '@/pages/LandingPage'

function page<K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) {
  return lazy(() => load().then((m) => ({ default: m[name] })))
}

const OverviewPage = page(() => import('@/pages/OverviewPage'), 'OverviewPage')
const SituationalPage = page(() => import('@/pages/SituationalPage'), 'SituationalPage')
const PlayersPage = page(() => import('@/pages/PlayersPage'), 'PlayersPage')
const ComparePage = page(() => import('@/pages/ComparePage'), 'ComparePage')
const UploadsPage = page(() => import('@/pages/UploadsPage'), 'UploadsPage')
const UploadDetailPage = page(() => import('@/pages/UploadDetailPage'), 'UploadDetailPage')
const ReportsPage = page(() => import('@/pages/ReportsPage'), 'ReportsPage')
const ReportDetailPage = page(() => import('@/pages/ReportDetailPage'), 'ReportDetailPage')
const JobsPage = page(() => import('@/pages/JobsPage'), 'JobsPage')

const NAV = [
  { to: '/overview', label: 'Overview' },
  { to: '/situational', label: 'Situational' },
  { to: '/players', label: 'Players' },
  { to: '/compare', label: 'Compare' },
  { to: '/uploads', label: 'My data' },
  { to: '/reports', label: 'Reports' },
  { to: '/jobs', label: 'Jobs' },
]

const navClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'shrink-0 rounded-md px-3 py-1.5 text-sm whitespace-nowrap transition-colors hover:bg-muted',
    isActive ? 'bg-muted font-medium text-foreground' : 'text-muted-foreground',
  )

function Lazy({ children, auth = false }: { children: ReactNode; auth?: boolean }) {
  const content = <Suspense fallback={<Skeleton className="h-96" aria-label="Loading page" />}>{children}</Suspense>
  return auth ? <RequireAuth>{content}</RequireAuth> : content
}

export function App() {
  return (
    <div className="flex min-h-svh flex-col">
      <header className="border-b print:hidden">
        <div className="mx-auto flex h-14 w-full max-w-7xl items-center gap-4 px-4 sm:px-6">
          <NavLink to="/" className="flex shrink-0 items-center gap-2 font-semibold tracking-tight">
            <span className="grid size-7 place-items-center rounded-md bg-primary text-xs text-primary-foreground">
              IQ
            </span>
            PlaybookIQ
          </NavLink>
          <nav className="hidden min-w-0 items-center gap-1 overflow-x-auto md:flex" aria-label="Main">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} className={navClass}>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <ThemeToggle />
            <UserMenu />
          </div>
        </div>
        <nav
          className="mx-auto flex w-full max-w-7xl gap-1 overflow-x-auto px-4 pb-2 sm:px-6 md:hidden"
          aria-label="Main (mobile)"
        >
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} className={navClass}>
              {n.label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 print:max-w-none print:p-0">
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<AuthPage mode="login" />} />
          <Route path="/register" element={<AuthPage mode="register" />} />
          <Route path="/overview" element={<Lazy><OverviewPage /></Lazy>} />
          <Route path="/situational" element={<Lazy><SituationalPage /></Lazy>} />
          <Route path="/players" element={<Lazy><PlayersPage /></Lazy>} />
          <Route path="/compare" element={<Lazy><ComparePage /></Lazy>} />
          <Route path="/uploads" element={<Lazy auth><UploadsPage /></Lazy>} />
          <Route path="/uploads/:id" element={<Lazy auth><UploadDetailPage /></Lazy>} />
          <Route path="/reports" element={<Lazy auth><ReportsPage /></Lazy>} />
          <Route path="/reports/:id" element={<Lazy auth><ReportDetailPage /></Lazy>} />
          <Route path="/jobs" element={<Lazy><JobsPage /></Lazy>} />
          <Route path="*" element={<EmptyState title="Page not found">Try the Overview page.</EmptyState>} />
        </Routes>
      </main>

      <footer className="border-t print:hidden">
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
