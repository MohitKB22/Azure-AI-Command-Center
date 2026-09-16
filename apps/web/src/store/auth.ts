import { create } from 'zustand'

import type { User } from '@/lib/types'

interface AuthState {
  token: string | null
  user: User | null
  permissions: string[]
  demoMode: boolean
  environment: string
  setSession: (token: string, user: User) => void
  setContext: (permissions: string[], demoMode: boolean, environment: string) => void
  clear: () => void
  can: (permission: string) => boolean
}

/**
 * Session state lives in memory only. The token is deliberately not persisted
 * to localStorage — that keeps it out of reach of any injected script, at the
 * cost of requiring a fresh sign-in per tab.
 */
export const useAuthStore = create<AuthState>((set, get) => ({
  token: null,
  user: null,
  permissions: [],
  demoMode: false,
  environment: 'local',
  setSession: (token, user) => set({ token, user }),
  setContext: (permissions, demoMode, environment) => set({ permissions, demoMode, environment }),
  clear: () => set({ token: null, user: null, permissions: [] }),
  can: (permission) => get().permissions.includes(permission),
}))
