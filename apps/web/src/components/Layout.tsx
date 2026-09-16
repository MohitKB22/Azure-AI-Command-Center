import clsx from 'clsx'
import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'

import { api } from '@/lib/api'
import { useAuthStore } from '@/store/auth'

const NAV = [
  { to: '/', label: 'Overview', end: true },
  { to: '/agents', label: 'Agents' },
  { to: '/runs', label: 'Agent Runs' },
  { to: '/rag', label: 'RAG' },
  { to: '/documents', label: 'Documents' },
  { to: '/prompts', label: 'Prompts' },
  { to: '/models', label: 'Models' },
  { to: '/azure', label: 'Azure Monitor' },
  { to: '/evaluations', label: 'Evaluations' },
  { to: '/guardrails', label: 'Guardrails' },
  { to: '/costs', label: 'Cost & Usage' },
  { to: '/alerts', label: 'Alerts' },
  { to: '/audit', label: 'Audit Logs' },
  { to: '/settings', label: 'Settings' },
]

export function Layout() {
  const navigate = useNavigate()
  const { user, environment, demoMode, clear } = useAuthStore()
  const [open, setOpen] = useState(false)

  async function signOut() {
    try {
      await api.post('/auth/logout')
    } catch {
      /* logging out locally is enough even if the call fails */
    }
    clear()
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex min-h-screen">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded focus:bg-azure-500 focus:px-3 focus:py-2 focus:text-white"
      >
        Skip to content
      </a>

      <aside
        className={clsx(
          'fixed inset-y-0 left-0 z-40 w-60 shrink-0 border-r border-border bg-surface/95 backdrop-blur transition-transform lg:static lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex h-14 items-center gap-2 border-b border-border px-4">
          <span className="grid h-7 w-7 place-items-center rounded bg-azure-500 text-xs font-bold text-white">
            AI
          </span>
          <div className="leading-tight">
            <p className="text-sm font-semibold text-white">Command Center</p>
            <p className="text-[10px] uppercase tracking-wider text-slate-400">Azure AI</p>
          </div>
        </div>

        <nav className="flex flex-col gap-0.5 p-2" aria-label="Primary">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                clsx(
                  'rounded-md px-3 py-2 text-sm transition-colors',
                  isActive
                    ? 'bg-azure-500/15 font-medium text-azure-100 ring-1 ring-inset ring-azure-500/30'
                    : 'text-slate-400 hover:bg-elevated hover:text-slate-100',
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      {open && (
        <button
          type="button"
          aria-label="Close navigation"
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={() => setOpen(false)}
        />
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-3 border-b border-border bg-canvas/85 px-4 backdrop-blur">
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="btn-ghost px-2 py-1 lg:hidden"
              onClick={() => setOpen((value) => !value)}
              aria-label="Toggle navigation"
            >
              ☰
            </button>
            <span className="rounded border border-border px-2 py-0.5 text-[11px] uppercase tracking-wide text-slate-400">
              {environment}
            </span>
            {demoMode && (
              <span className="rounded border border-cyanx/30 bg-cyanx/10 px-2 py-0.5 text-[11px] text-cyan-200">
                demo data
              </span>
            )}
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <p className="text-xs font-medium text-slate-200">{user?.full_name}</p>
              <p className="text-[11px] text-slate-500">{user?.role.replace('_', ' ')}</p>
            </div>
            <button type="button" className="btn-ghost" onClick={signOut}>
              Sign out
            </button>
          </div>
        </header>

        <main id="main" className="min-w-0 flex-1 p-4 lg:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
