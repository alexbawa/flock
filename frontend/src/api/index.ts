import type { JobResult, TripSubmission } from '../types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${text}`)
  }
  return res.json() as Promise<T>
}

export async function submitTrip(submission: TripSubmission): Promise<{ job_id: string }> {
  return request('/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(submission),
  })
}

export async function getJob(jobId: string): Promise<JobResult> {
  return request(`/jobs/${jobId}`)
}
