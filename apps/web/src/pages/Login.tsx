import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Field } from '@/components/ui'
import { ApiError, api } from '@/lib/api'
import type { User } from '@/lib/types'
import { useAuthStore } from '@/store/auth'

interface LoginResponse {
  access_token: string
  expires_at: string
  user: User
}

interface MeResponse {
  user: User
  permissions: string[]
  demo_mode: boolean
  environment: string
}

export function LoginPage() {
  const navigate = useNavigate()
  const { setSession, setContext } = useAuthStore()
  const [email, setEmail] = useState('admin@contoso.com')
  const [password, setPassword] = useState('')

  const login = useMutation({
    mutationFn: async () => {
      const session = await api.post<LoginResponse>('/auth/login', { email, password })
      setSession(session.access_token, session.user)
      const me = await api.get<MeResponse>('/auth/me')
      setContext(me.permissions, me.demo_mode, me.environment)
      return session
    },
    onSuccess: () => navigate('/', { replace: true }),
  })

  const message =
    login.error instanceof ApiError
      ? login.error.message
      : login.error
        ? 'Unable to reach the API. Is it running on port 8000?'
        : null

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="panel w-full max-w-md p-6">
        <div className="mb-6 flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded bg-azure-500 text-sm font-bold text-white">
            AI
          </span>
          <div>
            <h1 className="text-lg font-semibold text-white">Azure AI Command Center</h1>
            <p className="text-xs text-slate-400">Sign in to the control plane</p>
          </div>
        </div>

        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            login.mutate()
          }}
        >
          <Field label="Email" htmlFor="email">
            <input
              id="email"
              type="email"
              autoComplete="username"
              required
              className="field"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </Field>

          <Field label="Password" htmlFor="password">
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              className="field"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>

          {message && (
            <p role="alert" className="rounded border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-red-200">
              {message}
            </p>
          )}

          <button type="submit" className="btn-primary w-full" disabled={login.isPending}>
            {login.isPending ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <div className="mt-6 rounded-md border border-border bg-canvas px-3 py-2 text-[11px] leading-relaxed text-slate-400">
          <p className="font-medium text-slate-300">Demo credentials</p>
          <p className="mt-1 font-mono">admin@contoso.com · Passw0rd!Demo</p>
          <p className="mt-1">
            Other seeded roles use the same password: engineer@, dev@, analyst@, viewer@contoso.com.
          </p>
        </div>
      </div>
    </div>
  )
}
