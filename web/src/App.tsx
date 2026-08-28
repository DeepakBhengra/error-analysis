import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ApiError,
  defaultSearchWindow,
  fetchOrderModifyRequest,
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
  CurlPanelTab,
  CurlType,
  ErrorLookupResponse,
  OrderCreateTarget,
  OrderModifyTarget,
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
  const [curlTypes, setCurlTypes] = useState<CurlType[]>(['create'])
  const [curlPanelTab, setCurlPanelTab] = useState<CurlPanelTab>('create')
  const [mode, setMode] = useState<ReplayMode>('one_up')
  const [target, setTarget] = useState<OrderCreateTarget>('uat')
  const [modifyTarget, setModifyTarget] = useState<OrderModifyTarget>('test')
  const [tab, setTab] = useState<TabFilter>('all')
  const [results, setResults] = useState<SessionResult[]>([])
  const [createCurl, setCreateCurl] = useState('')
  const [modifyCurl, setModifyCurl] = useState('')
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
        setModifyTarget(settings.default_modify_target === 'qa1' ? 'qa1' : 'test')
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
    if (curlPanelTab === 'modify') {
      setModifyCurl(data.curl || '')
    } else {
      setCreateCurl(data.curl || '')
    }
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
    if (!query.trim() || loading || !curlTypes.length) return
    const controller = beginRequest()
    setLoading(true)
    setLoadingKind('preview')
    setError(null)
    setBannerOutcome(null)
    setBannerMessage('')
    setPreviewSource(null)
    setHttpResponse(null)

    const wantsCreate = curlTypes.includes('create')
    const wantsModify = curlTypes.includes('modify')
    if (!wantsCreate) setCreateCurl('')
    if (!wantsModify) setModifyCurl('')

    try {
      const searchParams = {
        text: query.trim(),
        from: toIsoZ(from),
        to: toIsoZ(to),
        signal: controller.signal,
      }

      const tasks: Promise<void>[] = []
      const messages: string[] = []

      if (wantsCreate) {
        tasks.push(
          fetchOrderRequest({ ...searchParams, target }).then((data) => {
            setCreateCurl(data.curl || '')
            setPreviewSource(data.source)
            messages.push(data.message)
          }),
        )
      }

      if (wantsModify) {
        tasks.push(
          fetchOrderModifyRequest({ ...searchParams, target: modifyTarget }).then((data) => {
            setModifyCurl(data.curl || '')
            messages.push(data.message)
            if (!wantsCreate) {
              setPreviewSource(null)
            }
          }),
        )
      }

      await Promise.all(tasks)

      if (wantsModify && !wantsCreate) {
        setCurlPanelTab('modify')
      } else if (wantsCreate) {
        setCurlPanelTab('create')
      }

      setBannerOutcome('READY')
      setBannerMessage(messages.join(' '))
      setError(null)
    } catch (err) {
      if (isAbortError(err)) {
        setError(null)
        setBannerOutcome(null)
        setBannerMessage('Cancelled.')
        setCreateCurl('')
        setModifyCurl('')
        setHttpResponse(null)
        setPreviewSource(null)
      } else {
        const msg =
          err instanceof ApiError
            ? err.message
            : 'Unexpected error while preparing order curl request(s).'
        setError(msg)
        setBannerOutcome(null)
        setBannerMessage('')
        setCreateCurl('')
        setModifyCurl('')
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
    const activeCurl = curlPanelTab === 'modify' ? modifyCurl : createCurl
    if (!activeCurl.trim() || loading) return
    const controller = beginRequest()
    setLoading(true)
    setLoadingKind('submit')
    setError(null)
    try {
      const data = await resubmitCurl({ curl: activeCurl, mode, signal: controller.signal })
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
    setCreateCurl('')
    setModifyCurl('')
    setHttpResponse(null)
    setPreviewSource(null)
    setError(null)
    setBannerOutcome(null)
    setBannerMessage('')
    setTab('all')
    setCurlPanelTab('create')
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
          onSaved={({ mode: nextMode, target: nextTarget, modifyTarget: nextModifyTarget }) => {
            setMode(nextMode)
            setTarget(nextTarget)
            setModifyTarget(nextModifyTarget)
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
            curlTypes={curlTypes}
            loading={loading}
            canCancel={loadingKind === 'preview'}
            onQueryChange={setQuery}
            onFromChange={setFrom}
            onToChange={setTo}
            onCurlTypesChange={setCurlTypes}
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
            activeTab={curlPanelTab}
            onTabChange={setCurlPanelTab}
            showCreateTab={curlTypes.includes('create')}
            showModifyTab={curlTypes.includes('modify')}
            createCurl={createCurl}
            modifyCurl={modifyCurl}
            loading={loading}
            canCancel={loadingKind === 'submit'}
            httpResponse={httpResponse}
            onCreateChange={setCreateCurl}
            onModifyChange={setModifyCurl}
            onResubmit={handleResubmit}
            onCancel={handleCancel}
          />
        </>
      )}
    </AppShell>
  )
}
