import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ApiError,
  defaultSearchWindow,
  fetchOrderRequest,
  fetchSettings,
  isAbortError,
  lookupErrorCode,
  resolveErrorCode,
  resubmitCurl,
  toIsoZ,
} from './api'
import { AppShell, type AppView } from './components/AppShell'
import { Breadcrumbs } from './components/Breadcrumbs'
import { CurlEditor } from './components/CurlEditor'
import { ErrorCodeModal } from './components/ErrorCodeModal'
import { MetricCards } from './components/MetricCards'
import { ResultTabs } from './components/ResultTabs'
import { ResultsTable } from './components/ResultsTable'
import { SearchBar } from './components/SearchBar'
import { SettingsPage } from './components/SettingsPage'
import { StatusBanner } from './components/StatusBanner'
import type {
  CurlHttpResponse,
  ErrorLookupResponse,
  OrderCreateTarget,
  OrderRequestSource,
  Outcome,
  ReplayMode,
  SessionResult,
  TabFilter,
} from './types'

const windowDefaults = defaultSearchWindow()

function newId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export default function App() {
  const [view, setView] = useState<AppView>('home')
  const [query, setQuery] = useState('')
  const [from, setFrom] = useState(windowDefaults.from)
  const [to, setTo] = useState(windowDefaults.to)
  const [mode, setMode] = useState<ReplayMode>('one_up')
  const [target, setTarget] = useState<OrderCreateTarget>('uat')
  const [tab, setTab] = useState<TabFilter>('all')
  const [results, setResults] = useState<SessionResult[]>([])
  const [curl, setCurl] = useState('')
  const [httpResponse, setHttpResponse] = useState<CurlHttpResponse | null>(null)
  const [previewSource, setPreviewSource] = useState<OrderRequestSource | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadingKind, setLoadingKind] = useState<'preview' | 'submit' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [bannerOutcome, setBannerOutcome] = useState<Outcome | null>(null)
  const [bannerMessage, setBannerMessage] = useState('')
  const [timestamp] = useState(() => new Date().toLocaleString())
  const [lookupOpen, setLookupOpen] = useState(false)
  const [lookupCode, setLookupCode] = useState('')
  const [lookupLoading, setLookupLoading] = useState(false)
  const [lookupError, setLookupError] = useState<string | null>(null)
  const [lookupResult, setLookupResult] = useState<ErrorLookupResponse | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    ;(async () => {
      try {
        const settings = await fetchSettings(controller.signal)
        setMode(settings.default_mode === 'random' ? 'random' : 'one_up')
        setTarget(settings.default_target === 'qa' ? 'qa' : 'uat')
      } catch {
        /* keep defaults if settings unavailable */
      }
    })()
    return () => controller.abort()
  }, [])

  const successCount = results.filter((r) => r.outcome === 'SUCCESS').length
  const failedCount = results.filter((r) => r.outcome === 'FAILED').length
  const latestImpulse = results[0]?.globalorderid || ''

  const filtered = useMemo(() => {
    if (tab === 'success') return results.filter((r) => r.outcome === 'SUCCESS')
    if (tab === 'failed') return results.filter((r) => r.outcome === 'FAILED')
    return results
  }, [results, tab])

  const applySubmitResponse = (data: Awaited<ReturnType<typeof resubmitCurl>>) => {
    const row: SessionResult = {
      ...data,
      id: newId(),
      fetchedAt: new Date().toISOString(),
    }
    setResults((prev) => [row, ...prev])
    setCurl(data.curl || '')
    setHttpResponse({
      httpStatus: data.http_status ?? null,
      httpBody: data.http_body ?? null,
      curlRepaired: Boolean(data.curlRepaired),
      repairedFields: data.repairedFields ?? [],
      unresolvedFields: data.unresolvedFields ?? [],
      repairMessage: data.repairMessage ?? '',
    })
    setBannerOutcome(data.outcome)
    setBannerMessage(data.message)
    setError(null)
  }

  const beginRequest = () => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    return controller
  }

  const endRequest = (controller: AbortController) => {
    if (abortRef.current === controller) abortRef.current = null
  }

  const handleCancel = () => {
    abortRef.current?.abort()
  }

  const handleRun = async () => {
    if (!query.trim() || loading) return
    const controller = beginRequest()
    setLoading(true)
    setLoadingKind('preview')
    setError(null)
    setBannerOutcome(null)
    setBannerMessage('')
    setPreviewSource(null)
    try {
      const data = await fetchOrderRequest({
        text: query.trim(),
        from: toIsoZ(from),
        to: toIsoZ(to),
        target,
        signal: controller.signal,
      })
      setCurl(data.curl || '')
      setHttpResponse(null)
      setPreviewSource(data.source)
      setBannerOutcome('READY')
      setBannerMessage(data.message)
      setError(null)
    } catch (err) {
      if (isAbortError(err)) {
        setError(null)
        setBannerOutcome(null)
        setBannerMessage('Cancelled.')
        setCurl('')
        setHttpResponse(null)
        setPreviewSource(null)
      } else {
        const msg =
          err instanceof ApiError
            ? err.message
            : 'Unexpected error while preparing Order Create request.'
        setError(msg)
        setBannerOutcome(null)
        setBannerMessage('')
        setCurl('')
        setHttpResponse(null)
        setPreviewSource(null)
      }
    } finally {
      endRequest(controller)
      setLoading(false)
      setLoadingKind(null)
    }
  }

  const handleResubmit = async () => {
    if (!curl.trim() || loading) return
    const controller = beginRequest()
    setLoading(true)
    setLoadingKind('submit')
    setError(null)
    try {
      const data = await resubmitCurl({ curl, mode, signal: controller.signal })
      applySubmitResponse(data)
    } catch (err) {
      if (isAbortError(err)) {
        setError(null)
        setBannerOutcome(null)
        setBannerMessage('Cancelled.')
      } else {
        const msg =
          err instanceof ApiError ? err.message : 'Unexpected error while re-submitting curl.'
        setError(msg)
      }
    } finally {
      endRequest(controller)
      setLoading(false)
      setLoadingKind(null)
    }
  }

  const handleRefresh = () => {
    abortRef.current?.abort()
    abortRef.current = null
    setLoading(false)
    setLoadingKind(null)
    setResults([])
    setCurl('')
    setHttpResponse(null)
    setPreviewSource(null)
    setError(null)
    setBannerOutcome(null)
    setBannerMessage('')
    setTab('all')
    setLookupOpen(false)
    setLookupCode('')
    setLookupError(null)
    setLookupResult(null)
  }

  const handleCloseLookup = () => {
    setLookupOpen(false)
    setLookupLoading(false)
    setLookupError(null)
    setLookupResult(null)
  }

  const handleErrorCodeClick = async (code: string) => {
    if (!code.trim() || lookupLoading) return
    setLookupOpen(true)
    setLookupCode(code)
    setLookupLoading(true)
    setLookupError(null)
    setLookupResult(null)
    try {
      const data = await lookupErrorCode(code)
      setLookupResult(data)
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : 'Unexpected error while looking up error code.'
      setLookupError(msg)
    } finally {
      setLookupLoading(false)
    }
  }

  const handleResolveClick = async (row: SessionResult) => {
    const code = row.statuscode?.trim()
    if (!code || lookupLoading) return
    setLookupOpen(true)
    setLookupCode(code)
    setLookupLoading(true)
    setLookupError(null)
    setLookupResult(null)
    try {
      const data = await resolveErrorCode(code)
      setLookupResult(data.result)
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : 'Unexpected error while resolving error code.'
      setLookupError(msg)
    } finally {
      setLookupLoading(false)
    }
  }

  return (
    <AppShell view={view} onNavigate={setView}>
      <Breadcrumbs timestamp={timestamp} view={view} />
      {view === 'settings' ? (
        <SettingsPage
          onSaved={({ mode: nextMode, target: nextTarget }) => {
            setMode(nextMode)
            setTarget(nextTarget)
          }}
        />
      ) : (
        <>
          <MetricCards
            runs={results.length}
            success={successCount}
            failed={failedCount}
            impulseOrder={latestImpulse}
          />
          <ResultTabs
            tab={tab}
            allCount={results.length}
            successCount={successCount}
            failedCount={failedCount}
            onChange={setTab}
          />
          <SearchBar
            query={query}
            from={from}
            to={to}
            loading={loading}
            canCancel={loadingKind === 'preview'}
            onQueryChange={setQuery}
            onFromChange={setFrom}
            onToChange={setTo}
            onRun={handleRun}
            onCancel={handleCancel}
            onRefresh={handleRefresh}
          />
          <StatusBanner
            outcome={bannerOutcome}
            message={bannerMessage}
            loading={loading}
            loadingKind={loadingKind}
            error={error}
            previewSource={previewSource}
          />
          <ResultsTable
            rows={filtered}
            onErrorCodeClick={handleErrorCodeClick}
            onResolveClick={handleResolveClick}
            resolvingCode={lookupLoading ? lookupCode : null}
          />
          <ErrorCodeModal
            open={lookupOpen}
            errorCode={lookupCode}
            loading={lookupLoading}
            error={lookupError}
            result={lookupResult}
            onClose={handleCloseLookup}
          />
          <CurlEditor
            curl={curl}
            loading={loading}
            canCancel={loadingKind === 'submit'}
            httpResponse={httpResponse}
            onChange={setCurl}
            onResubmit={handleResubmit}
            onCancel={handleCancel}
          />
        </>
      )}
    </AppShell>
  )
}
