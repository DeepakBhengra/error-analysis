import type { SessionResult } from '../types'

interface ResultsTableProps {
  rows: SessionResult[]
  onErrorCodeClick?: (code: string, row: SessionResult) => void
  onResolveClick?: (row: SessionResult) => void
  resolvingCode?: string | null
}

export function ResultsTable({
  rows,
  onErrorCodeClick,
  onResolveClick,
  resolvingCode,
}: ResultsTableProps) {
  return (
    <div className="table-wrap">
      <table className="results-table">
        <thead>
          <tr>
            <th>Status</th>
            <th>Error Code</th>
            <th>Error Message</th>
            <th>Impulse Order Number</th>
            <th>Customer Order Number</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={5} className="empty-cell">
                No results yet. Enter a customer order number and click RUN.
              </td>
            </tr>
          ) : (
            rows.map((row) => {
              const status = (row.responsestatus || row.outcome || '').toUpperCase()
              const isSuccess = status === 'SUCCESS'
              const canResolve = Boolean(row.statuscode) && !isSuccess
              return (
              <tr key={row.id}>
                <td>{row.responsestatus || row.outcome}</td>
                <td>
                  {row.statuscode ? (
                    <button
                      type="button"
                      className="error-code-link"
                      onClick={() => onErrorCodeClick?.(row.statuscode, row)}
                    >
                      {row.statuscode}
                    </button>
                  ) : (
                    '—'
                  )}
                </td>
                <td className="msg-cell">{row.responsemessage || '—'}</td>
                <td>{row.globalorderid || '—'}</td>
                <td>
                  <div className="order-number-cell">
                    <span>{row.customerOrderNumber || '—'}</span>
                    {row.statuscode ? (
                      <button
                        type="button"
                        className="btn-resolve"
                        onClick={() => onResolveClick?.(row)}
                        disabled={!canResolve || resolvingCode === row.statuscode}
                      >
                        {resolvingCode === row.statuscode ? 'Resolving…' : 'Resolve'}
                      </button>
                    ) : null}
                  </div>
                </td>
              </tr>
              )
            })
          )}
        </tbody>
      </table>
    </div>
  )
}
