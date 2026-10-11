import { useCallback, useLayoutEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'

type Next = URLSearchParams | ((prev: URLSearchParams) => URLSearchParams)

/**
 * `useSearchParams`, but updates always build on the latest params.
 *
 * React Router passes the function form the params of the last render, so two updates
 * made before a re-render (two quick picks, browser automation) lose the first one.
 * Updates here replace the history entry, which is what URL-backed filters want.
 */
export function useUrlParams(): [URLSearchParams, (next: Next) => void] {
  const [params, setParams] = useSearchParams()
  const latest = useRef(params)
  useLayoutEffect(() => {
    latest.current = params
  }, [params])

  const update = useCallback(
    (next: Next) => {
      const value = typeof next === 'function' ? next(latest.current) : next
      latest.current = value
      setParams(value, { replace: true })
    },
    [setParams],
  )
  return [params, update]
}
