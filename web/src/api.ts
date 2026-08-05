import type {
  AppSettings,
  AppSettingsUpdate,
  ErrorLookupResponse,
  OrderRequestPreviewResponse,
  ReplayApiResponse,
  ReplayMode,
  OrderCreateTarget,
  ResolveErrorResponse,
} from './types'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export function isAbortError(err: unknown): boolean {
  return (
    (err instanceof DOMException && err.name === 'AbortError') ||
    (err instanceof Error && err.name === 'AbortError')
  )
}

async function parseError(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: string | { msg?: string }[] }
    if (typeof data.detail === 'string') return data.detail
    if (Array.isArray(data.detail)) {
      return data.detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
    }
  } catch {
    /* ignore — proxy 502 often returns plain text / empty body */
  }
  // Vite proxy returns bare "Bad Gateway" when nothing is listening on :8010
  if (res.status === 502) {
    return (
      'API server unreachable (Bad Gateway). ' +
      'Start the API on http://127.0.0.1:8010 — from the repo root run ' +
      'error-analysis-api, or in VS Code use task "Error Analysis: API + UI", ' +
      'or restart npm run dev (it auto-starts the API when .venv is installed).'
    )
  }
  return res.statusText || `Request failed (${res.status})`
}

export async function fetchOrderRequest(params: {
  text: string
  from?: string
  to?: string
  target?: OrderCreateTarget
  signal?: AbortSignal
}): Promise<OrderRequestPreviewResponse> {
  const res = await fetch('/api/order-request', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: params.text,
      from: params.from,
      to: params.to,
      target: params.target ?? 'uat',
    }),
    signal: params.signal,
  })
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
  return res.json() as Promise<OrderRequestPreviewResponse>
}

export async function runReplay(params: {
  text: string
  from?: string
  to?: string
  mode: ReplayMode
  target?: OrderCreateTarget
  signal?: AbortSignal
}): Promise<ReplayApiResponse> {
  const res = await fetch('/api/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: params.text,
      from: params.from,
      to: params.to,
      mode: params.mode,
      target: params.target ?? 'uat',
    }),
    signal: params.signal,
  })
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
  return res.json() as Promise<ReplayApiResponse>
}

export async function resubmitCurl(params: {
  curl: string
  mode: ReplayMode
  signal?: AbortSignal
}): Promise<ReplayApiResponse> {
  const res = await fetch('/api/resubmit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      curl: params.curl,
      mode: params.mode,
    }),
    signal: params.signal,
  })
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
  return res.json() as Promise<ReplayApiResponse>
}

export async function lookupErrorCode(errorCode: string): Promise<ErrorLookupResponse> {
  const res = await fetch('/api/error-lookup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ error_code: errorCode }),
  })
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
  return res.json() as Promise<ErrorLookupResponse>
}

export async function resolveErrorCode(errorCode: string): Promise<ResolveErrorResponse> {
  const res = await fetch('/api/resolve-error', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ error_code: errorCode }),
  })
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
  return res.json() as Promise<ResolveErrorResponse>
}

export async function fetchSettings(signal?: AbortSignal): Promise<AppSettings> {
  const res = await fetch('/api/settings', { signal })
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
  return res.json() as Promise<AppSettings>
}

export async function updateSettings(payload: AppSettingsUpdate): Promise<AppSettings> {
  const res = await fetch('/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
  return res.json() as Promise<AppSettings>
}

export function defaultSearchWindow(): { from: string; to: string } {
  const to = new Date()
  const from = new Date(to.getTime() - 30 * 24 * 60 * 60 * 1000)
  return {
    from: from.toISOString().slice(0, 16),
    to: to.toISOString().slice(0, 16),
  }
}

export function toIsoZ(localDatetime: string): string {
  if (!localDatetime) return ''
  const d = new Date(localDatetime)
  if (Number.isNaN(d.getTime())) return localDatetime
  return d.toISOString().replace(/\.\d{3}Z$/, 'Z')
}
