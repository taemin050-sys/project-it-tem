import type { ReactNode } from 'react'

type Props = {
  id: string
  label: string
  required?: boolean
  hint?: string
  error?: string
  children: ReactNode
}

// 입력 요소에는 aria-describedby={`${id}-hint ${id}-error`} 중 있는 것을 연결한다
export default function Field({ id, label, required, hint, error, children }: Props) {
  return (
    <div className={error ? 'field has-error' : 'field'}>
      <label htmlFor={id} className="field-label">
        {label}
        <span className="field-tag">{required ? '필수' : '선택'}</span>
      </label>
      {children}
      {hint && <p id={`${id}-hint`} className="field-hint">{hint}</p>}
      {error && <p id={`${id}-error`} className="field-error">{error}</p>}
    </div>
  )
}
