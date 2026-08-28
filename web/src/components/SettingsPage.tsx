import { useEffect, useState, type FormEvent } from 'react'
import { ApiError, fetchSettings, isAbortError, updateSettings } from '../api'
import type { AppSettings, OrderCreateTarget, OrderModifyTarget, ReplayMode } from '../types'

interface SettingsPageProps {
  onSaved: (defaults: {
    mode: ReplayMode
    target: OrderCreateTarget
    modifyTarget: OrderModifyTarget
  }) => void
}

const emptyForm = {
  dd_api_key: '',
  dd_app_key: '',
  dd_access_token: '',
  dd_site: 'us5.datadoghq.com',
  order_create_username: '',
  order_create_password: '',
  order_create_cookie: '',
  order_modify_test_username: '',
  order_modify_test_password: '',
  order_modify_qa1_username: '',
  order_modify_qa1_password: '',
  default_target: 'uat' as OrderCreateTarget,
  default_modify_target: 'test' as OrderModifyTarget,
  default_mode: 'one_up' as ReplayMode,
}

export function SettingsPage({ onSaved }: SettingsPageProps) {
  const [form, setForm] = useState(emptyForm)
  const [configured, setConfigured] = useState({
    dd_api_key: false,
    dd_app_key: false,
    dd_access_token: false,
    order_create_password: false,
    order_create_cookie: false,
    order_modify_test_password: false,
    order_modify_qa1_password: false,
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    ;(async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await fetchSettings(controller.signal)
        applySettings(data)
      } catch (err) {
        if (isAbortError(err)) return
        setError(err instanceof ApiError ? err.message : 'Failed to load settings')
      } finally {
        setLoading(false)
      }
    })()
    return () => controller.abort()
  }, [])

  const applySettings = (data: AppSettings) => {
    setForm({
      dd_api_key: '',
      dd_app_key: '',
      dd_access_token: '',
      dd_site: data.dd_site || 'us5.datadoghq.com',
      order_create_username: data.order_create_username || '',
      order_create_password: '',
      order_create_cookie: '',
      order_modify_test_username: data.order_modify_test_username || '',
      order_modify_test_password: '',
      order_modify_qa1_username: data.order_modify_qa1_username || '',
      order_modify_qa1_password: '',
      default_target: data.default_target === 'qa' ? 'qa' : 'uat',
      default_modify_target: data.default_modify_target === 'qa1' ? 'qa1' : 'test',
      default_mode: data.default_mode === 'random' ? 'random' : 'one_up',
    })
    setConfigured({
      dd_api_key: data.dd_api_key_configured,
      dd_app_key: data.dd_app_key_configured,
      dd_access_token: data.dd_access_token_configured,
      order_create_password: data.order_create_password_configured,
      order_create_cookie: data.order_create_cookie_configured,
      order_modify_test_password: data.order_modify_test_password_configured,
      order_modify_qa1_password: data.order_modify_qa1_password_configured,
    })
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (saving) return
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const payload = {
        dd_site: form.dd_site.trim(),
        order_create_username: form.order_create_username.trim(),
        default_target: form.default_target,
        default_modify_target: form.default_modify_target,
        default_mode: form.default_mode,
        order_modify_test_username: form.order_modify_test_username.trim(),
        order_modify_qa1_username: form.order_modify_qa1_username.trim(),
        ...(form.dd_api_key.trim() ? { dd_api_key: form.dd_api_key.trim() } : {}),
        ...(form.dd_app_key.trim() ? { dd_app_key: form.dd_app_key.trim() } : {}),
        ...(form.dd_access_token.trim()
          ? { dd_access_token: form.dd_access_token.trim() }
          : {}),
        ...(form.order_create_password.trim()
          ? { order_create_password: form.order_create_password.trim() }
          : {}),
        ...(form.order_create_cookie.trim()
          ? { order_create_cookie: form.order_create_cookie.trim() }
          : {}),
        ...(form.order_modify_test_password.trim()
          ? { order_modify_test_password: form.order_modify_test_password.trim() }
          : {}),
        ...(form.order_modify_qa1_password.trim()
          ? { order_modify_qa1_password: form.order_modify_qa1_password.trim() }
          : {}),
      }
      const data = await updateSettings(payload)
      applySettings(data)
      onSaved({
        mode: data.default_mode,
        target: data.default_target,
        modifyTarget: data.default_modify_target,
      })
      setMessage('Settings saved.')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="settings-page">
      <h1 className="settings-title">Settings</h1>
      <p className="settings-intro">
        Configure replay defaults and credentials used for Datadog search and Order Create curl
        (build-order-curl).
      </p>

      {loading ? <p className="settings-status">Loading settings…</p> : null}
      {error ? <p className="settings-error">{error}</p> : null}
      {message ? <p className="settings-success">{message}</p> : null}

      <form className="settings-form" onSubmit={handleSubmit}>
        <fieldset className="settings-section" disabled={loading || saving}>
          <legend>Replay defaults</legend>
          <p className="settings-hint">Home uses these when building and re-submitting orders.</p>
          <div className="settings-row">
            <fieldset className="mode-fieldset">
              <legend className="sr-only">Order Create target</legend>
              <label className="mode-option">
                <input
                  type="radio"
                  name="default_target"
                  checked={form.default_target === 'uat'}
                  onChange={() => setForm((prev) => ({ ...prev, default_target: 'uat' }))}
                />
                UAT
              </label>
              <label className="mode-option">
                <input
                  type="radio"
                  name="default_target"
                  checked={form.default_target === 'qa'}
                  onChange={() => setForm((prev) => ({ ...prev, default_target: 'qa' }))}
                />
                QA
              </label>
            </fieldset>
            <fieldset className="mode-fieldset">
              <legend className="sr-only">Order Modify target</legend>
              <label className="mode-option">
                <input
                  type="radio"
                  name="default_modify_target"
                  checked={form.default_modify_target === 'test'}
                  onChange={() =>
                    setForm((prev) => ({ ...prev, default_modify_target: 'test' }))
                  }
                />
                api-test
              </label>
              <label className="mode-option">
                <input
                  type="radio"
                  name="default_modify_target"
                  checked={form.default_modify_target === 'qa1'}
                  onChange={() =>
                    setForm((prev) => ({ ...prev, default_modify_target: 'qa1' }))
                  }
                />
                api-qa1
              </label>
            </fieldset>
            <fieldset className="mode-fieldset">
              <legend className="sr-only">Order number mode</legend>
              <label className="mode-option">
                <input
                  type="radio"
                  name="default_mode"
                  checked={form.default_mode === 'one_up'}
                  onChange={() => setForm((prev) => ({ ...prev, default_mode: 'one_up' }))}
                />
                One-up
              </label>
              <label className="mode-option">
                <input
                  type="radio"
                  name="default_mode"
                  checked={form.default_mode === 'random'}
                  onChange={() => setForm((prev) => ({ ...prev, default_mode: 'random' }))}
                />
                Random
              </label>
            </fieldset>
          </div>
        </fieldset>

        <fieldset className="settings-section" disabled={loading || saving}>
          <legend>Datadog</legend>
          <p className="settings-hint">
            Prefer a Personal/Service Access Token (`DD_ACCESS_TOKEN`). Classic API + App keys are
            used only when the access token is empty.
          </p>
          <label className="settings-field">
            <span>DD access token</span>
            <input
              type="password"
              autoComplete="off"
              placeholder={
                configured.dd_access_token
                  ? 'Configured — leave blank to keep'
                  : 'DD_ACCESS_TOKEN (PAT / SAT)'
              }
              value={form.dd_access_token}
              onChange={(e) => setForm((prev) => ({ ...prev, dd_access_token: e.target.value }))}
            />
          </label>
          <label className="settings-field">
            <span>DD API key</span>
            <input
              type="password"
              autoComplete="off"
              placeholder={configured.dd_api_key ? 'Configured — leave blank to keep' : 'DD_API_KEY'}
              value={form.dd_api_key}
              onChange={(e) => setForm((prev) => ({ ...prev, dd_api_key: e.target.value }))}
            />
          </label>
          <label className="settings-field">
            <span>DD App key</span>
            <input
              type="password"
              autoComplete="off"
              placeholder={configured.dd_app_key ? 'Configured — leave blank to keep' : 'DD_APP_KEY'}
              value={form.dd_app_key}
              onChange={(e) => setForm((prev) => ({ ...prev, dd_app_key: e.target.value }))}
            />
          </label>
          <label className="settings-field">
            <span>DD site</span>
            <input
              type="text"
              autoComplete="off"
              value={form.dd_site}
              onChange={(e) => setForm((prev) => ({ ...prev, dd_site: e.target.value }))}
            />
          </label>
        </fieldset>

        <fieldset className="settings-section" disabled={loading || saving}>
          <legend>Order Create Basic Auth</legend>
          <p className="settings-hint">Used for build-order-curl / order-request preview and replay.</p>
          <label className="settings-field">
            <span>Username</span>
            <input
              type="text"
              autoComplete="off"
              value={form.order_create_username}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, order_create_username: e.target.value }))
              }
            />
          </label>
          <label className="settings-field">
            <span>Password</span>
            <input
              type="password"
              autoComplete="off"
              placeholder={
                configured.order_create_password ? 'Configured — leave blank to keep' : ''
              }
              value={form.order_create_password}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, order_create_password: e.target.value }))
              }
            />
          </label>
          <label className="settings-field">
            <span>Cookie (optional)</span>
            <input
              type="password"
              autoComplete="off"
              placeholder={
                configured.order_create_cookie ? 'Configured — leave blank to keep' : ''
              }
              value={form.order_create_cookie}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, order_create_cookie: e.target.value }))
              }
            />
          </label>
        </fieldset>

        <fieldset className="settings-section" disabled={loading || saving}>
          <legend>Order Modify Basic Auth (api-test)</legend>
          <p className="settings-hint">
            Credentials for PUT https://api-test.ingrammicro.com/resellers/v6/orders/…
          </p>
          <label className="settings-field">
            <span>Username</span>
            <input
              type="text"
              autoComplete="off"
              value={form.order_modify_test_username}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, order_modify_test_username: e.target.value }))
              }
            />
          </label>
          <label className="settings-field">
            <span>Password</span>
            <input
              type="password"
              autoComplete="off"
              placeholder={
                configured.order_modify_test_password
                  ? 'Configured — leave blank to keep'
                  : ''
              }
              value={form.order_modify_test_password}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, order_modify_test_password: e.target.value }))
              }
            />
          </label>
        </fieldset>

        <fieldset className="settings-section" disabled={loading || saving}>
          <legend>Order Modify Basic Auth (api-qa1)</legend>
          <p className="settings-hint">
            Credentials for PUT https://api-qa1.ingrammicro.com/resellers/v6/orders/…
          </p>
          <label className="settings-field">
            <span>Username</span>
            <input
              type="text"
              autoComplete="off"
              value={form.order_modify_qa1_username}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, order_modify_qa1_username: e.target.value }))
              }
            />
          </label>
          <label className="settings-field">
            <span>Password</span>
            <input
              type="password"
              autoComplete="off"
              placeholder={
                configured.order_modify_qa1_password
                  ? 'Configured — leave blank to keep'
                  : ''
              }
              value={form.order_modify_qa1_password}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, order_modify_qa1_password: e.target.value }))
              }
            />
          </label>
        </fieldset>

        <div className="settings-actions">
          <button type="submit" className="btn-outline-primary" disabled={loading || saving}>
            {saving ? 'Saving…' : 'Save settings'}
          </button>
        </div>
      </form>
    </section>
  )
}
