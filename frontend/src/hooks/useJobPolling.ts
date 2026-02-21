import { useEffect, useRef, useState } from 'react'
import { getJob } from '../api'
import type { JobResult } from '../types'

const POLL_INTERVAL_MS = 3000

export function useJobPolling(jobId: string | null) {
  const [result, setResult] = useState<JobResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!jobId) {
      setResult(null)
      setError(null)
      return
    }

    const poll = async () => {
      try {
        const data = await getJob(jobId)
        setResult(data)
        if (data.status === 'complete' || data.status === 'failed') {
          if (intervalRef.current !== null) {
            clearInterval(intervalRef.current)
            intervalRef.current = null
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
        if (intervalRef.current !== null) {
          clearInterval(intervalRef.current)
          intervalRef.current = null
        }
      }
    }

    poll()
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS)

    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [jobId])

  return { result, error }
}
