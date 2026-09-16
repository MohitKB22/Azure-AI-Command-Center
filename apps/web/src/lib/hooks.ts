import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'

import { api, qs } from '@/lib/api'
import type { Page } from '@/lib/types'

/** Debounce a rapidly changing value (search boxes). */
export function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

export interface PagedState {
  page: number
  setPage: (page: number) => void
  search: string
  setSearch: (value: string) => void
  sortBy: string | undefined
  sortDir: 'asc' | 'desc'
  toggleSort: (key: string) => void
}

/** List page state: search, sort and pagination wired to one query. */
export function usePagedList<T>(
  key: string,
  path: string,
  extra: Record<string, string | number | boolean | undefined> = {},
  pageSize = 20,
) {
  const [page, setPage] = useState(1)
  const [search, setSearchRaw] = useState('')
  const [sortBy, setSortBy] = useState<string | undefined>()
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const debouncedSearch = useDebounced(search)

  const setSearch = (value: string) => {
    setSearchRaw(value)
    setPage(1)
  }

  const toggleSort = (columnKey: string) => {
    if (sortBy === columnKey) {
      setSortDir((direction) => (direction === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortBy(columnKey)
      setSortDir('desc')
    }
    setPage(1)
  }

  const extraKey = JSON.stringify(extra)
  const query = useQuery({
    queryKey: [key, page, debouncedSearch, sortBy, sortDir, extraKey],
    queryFn: () =>
      api.get<Page<T>>(
        `${path}${qs({
          page,
          page_size: pageSize,
          q: debouncedSearch || undefined,
          sort_by: sortBy,
          sort_dir: sortDir,
          ...extra,
        })}`,
      ),
    placeholderData: keepPreviousData,
  })

  const state: PagedState = useMemo(
    () => ({ page, setPage, search, setSearch, sortBy, sortDir, toggleSort }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [page, search, sortBy, sortDir],
  )

  return { ...query, state }
}
