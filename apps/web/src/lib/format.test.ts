import { describe, expect, it } from 'vitest'

import {
  formatBytes,
  formatCurrency,
  formatDuration,
  formatNumber,
  formatPercent,
  titleCase,
} from './format'

describe('formatNumber', () => {
  it('formats integers with separators', () => {
    expect(formatNumber(1234567)).toBe((1234567).toLocaleString(undefined, { maximumFractionDigits: 0 }))
  })

  it('renders an em dash for missing values', () => {
    expect(formatNumber(null)).toBe('—')
    expect(formatNumber(undefined)).toBe('—')
    expect(formatNumber(Number.NaN)).toBe('—')
  })
})

describe('formatCurrency', () => {
  it('uses four decimals for sub-dollar amounts', () => {
    expect(formatCurrency(0.0123)).toContain('0.0123')
  })

  it('uses two decimals above a dollar', () => {
    expect(formatCurrency(12.3456)).toContain('12.35')
  })

  it('handles zero without crashing', () => {
    expect(formatCurrency(0)).toContain('0.00')
  })
})

describe('formatDuration', () => {
  it('renders milliseconds below a second', () => {
    expect(formatDuration(450)).toBe('450 ms')
  })

  it('renders seconds below a minute', () => {
    expect(formatDuration(2500)).toBe('2.50 s')
  })

  it('renders minutes and seconds above a minute', () => {
    expect(formatDuration(125_000)).toBe('2m 5s')
  })

  it('handles null', () => {
    expect(formatDuration(null)).toBe('—')
  })
})

describe('formatBytes', () => {
  it('scales units', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(900)).toBe('900 B')
    expect(formatBytes(2048)).toBe('2.0 KB')
    expect(formatBytes(5 * 1024 * 1024)).toBe('5.0 MB')
  })
})

describe('formatPercent', () => {
  it('appends a percent sign', () => {
    expect(formatPercent(12.345)).toBe('12.3%')
  })
})

describe('titleCase', () => {
  it('converts snake case to title case', () => {
    expect(titleCase('guardrail_input')).toBe('Guardrail Input')
    expect(titleCase('ai_engineer')).toBe('Ai Engineer')
  })
})
