import type { OrrorhField } from '../types'

interface Orrorh88PopupProps {
  field: OrrorhField | null
  onClose: () => void
}

function formatValues(values: string[]): string {
  return values.map((value) => (value === 'Spaces' ? "' '" : `'${value}'`)).join('  ')
}

export function Orrorh88Popup({ field, onClose }: Orrorh88PopupProps) {
  if (!field) return null
  const conditions = field.conditions ?? []

  return (
    <div className="modal-overlay" onClick={onClose} role="presentation">
      <div
        className="modal-panel orrorh-88-popup"
        role="dialog"
        aria-modal="true"
        aria-labelledby="orrorh-88-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <h2 id="orrorh-88-title">{field.name}</h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="modal-body">
          <p className="orrorh-88-current">
            Current value <strong>{field.value}</strong>
          </p>
          <p className="orrorh-88-hint">88 condition-names attached to this field</p>
          {conditions.length ? (
            <table className="orrorh-88-table">
              <thead>
                <tr>
                  <th>Condition</th>
                  <th>Values</th>
                  <th>Match</th>
                </tr>
              </thead>
              <tbody>
                {conditions.map((condition) => (
                  <tr
                    key={condition.name}
                    className={condition.matched ? 'orrorh-88-row-match' : undefined}
                  >
                    <td>
                      <code>{condition.name}</code>
                    </td>
                    <td>
                      <code>{formatValues(condition.values)}</code>
                    </td>
                    <td>{condition.matched ? 'True' : 'False'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="modal-status">No 88 condition-names for this field.</p>
          )}
        </div>
      </div>
    </div>
  )
}
