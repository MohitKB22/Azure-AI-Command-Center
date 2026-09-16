import { Navigate, Route, Routes } from 'react-router-dom'

import { Layout } from '@/components/Layout'
import { AgentDetailPage } from '@/pages/AgentDetail'
import { AgentsPage } from '@/pages/Agents'
import { AlertsPage } from '@/pages/Alerts'
import { AuditPage } from '@/pages/Audit'
import { AzureMonitorPage } from '@/pages/AzureMonitor'
import { CostsPage } from '@/pages/Costs'
import { DocumentsPage } from '@/pages/Documents'
import { EvaluationsPage } from '@/pages/Evaluations'
import { GuardrailsPage } from '@/pages/Guardrails'
import { LoginPage } from '@/pages/Login'
import { ModelsPage } from '@/pages/Models'
import { NotFoundPage } from '@/pages/NotFound'
import { OverviewPage } from '@/pages/Overview'
import { PromptsPage } from '@/pages/Prompts'
import { RagPage } from '@/pages/Rag'
import { RunDetailPage } from '@/pages/RunDetail'
import { RunsPage } from '@/pages/Runs'
import { SettingsPage } from '@/pages/Settings'
import { useAuthStore } from '@/store/auth'

function RequireAuth({ children }: { children: JSX.Element }) {
  const token = useAuthStore((state) => state.token)
  if (!token) return <Navigate to="/login" replace />
  return children
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<OverviewPage />} />
        <Route path="/agents" element={<AgentsPage />} />
        <Route path="/agents/:agentId" element={<AgentDetailPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:runId" element={<RunDetailPage />} />
        <Route path="/rag" element={<RagPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/prompts" element={<PromptsPage />} />
        <Route path="/models" element={<ModelsPage />} />
        <Route path="/azure" element={<AzureMonitorPage />} />
        <Route path="/evaluations" element={<EvaluationsPage />} />
        <Route path="/guardrails" element={<GuardrailsPage />} />
        <Route path="/costs" element={<CostsPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/audit" element={<AuditPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
