import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Badge, DataTable, EmptyState, ErrorState, Pagination, toneForStatus } from './ui'

describe('toneForStatus', () => {
  it('maps healthy states to success', () => {
    expect(toneForStatus('succeeded')).toBe('success')
    expect(toneForStatus('indexed')).toBe('success')
  })

  it('maps failures to danger', () => {
    expect(toneForStatus('failed')).toBe('danger')
    expect(toneForStatus('blocked')).toBe('danger')
  })

  it('maps in-flight states to warning', () => {
    expect(toneForStatus('running')).toBe('warning')
    expect(toneForStatus('degraded')).toBe('warning')
  })

  it('falls back to info for unknown values', () => {
    expect(toneForStatus('something-else')).toBe('info')
  })
})

describe('DataTable', () => {
  const rows = [
    { id: '1', name: 'Support Agent' },
    { id: '2', name: 'Runbook Agent' },
  ]
  const columns = [{ key: 'name', header: 'Name', render: (row: (typeof rows)[number]) => row.name }]

  it('renders every row', () => {
    render(<DataTable rows={rows} columns={columns} keyOf={(row) => row.id} />)
    expect(screen.getByText('Support Agent')).toBeInTheDocument()
    expect(screen.getByText('Runbook Agent')).toBeInTheDocument()
  })

  it('shows the empty state when there are no rows', () => {
    render(<DataTable rows={[]} columns={columns} keyOf={() => 'x'} emptyMessage="Nothing here" />)
    expect(screen.getByText('Nothing here')).toBeInTheDocument()
  })

  it('calls onRowClick', async () => {
    const onRowClick = vi.fn()
    render(<DataTable rows={rows} columns={columns} keyOf={(row) => row.id} onRowClick={onRowClick} />)
    await userEvent.click(screen.getByText('Support Agent'))
    expect(onRowClick).toHaveBeenCalledWith(rows[0])
  })
})

describe('Pagination', () => {
  it('disables previous on the first page', () => {
    render(<Pagination page={1} pages={3} total={60} onChange={() => undefined} />)
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled()
  })

  it('renders nothing when there are no records', () => {
    const { container } = render(<Pagination page={1} pages={1} total={0} onChange={() => undefined} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('states', () => {
  it('renders an error message', () => {
    render(<ErrorState error={new Error('Boom')} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Boom')
  })

  it('renders an empty state with a description', () => {
    render(<EmptyState title="No agents" description="Create one to begin" />)
    expect(screen.getByText('Create one to begin')).toBeInTheDocument()
  })

  it('renders badges', () => {
    render(<Badge tone="danger">blocked</Badge>)
    expect(screen.getByText('blocked')).toBeInTheDocument()
  })
})
