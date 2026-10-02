import { useState } from 'react'

interface CopyButtonProps {
  text: string
  label: string
}

async function writeClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  const el = document.createElement('textarea')
  el.value = text
  el.setAttribute('readonly', '')
  el.style.position = 'fixed'
  el.style.left = '-9999px'
  document.body.appendChild(el)
  el.select()
  document.execCommand('copy')
  document.body.removeChild(el)
}

export function CopyButton({ text, label }: CopyButtonProps) {
  const [copied, setCopied] = useState(false)

  const onCopy = async () => {
    const value = text.trim()
    if (!value) return
    try {
      await writeClipboard(text)
    } catch {
      return
    }
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }

  return (
    <button
      type="button"
      className={`btn-copy${copied ? ' is-copied' : ''}`}
      onClick={() => void onCopy()}
      disabled={!text.trim()}
      aria-label={copied ? 'Copied' : label}
      title={copied ? 'Copied' : label}
    >
      {copied ? (
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden>
          <path d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden>
          <path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z" />
        </svg>
      )}
    </button>
  )
}
