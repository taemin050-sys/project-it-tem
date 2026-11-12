export type Option<T extends string> = { value: T; label: string; desc?: string }

type Props<T extends string> = {
  legend: string
  name: string
  options: readonly Option<T>[]
  value: T
  onChange: (value: T) => void
  disabled?:boolean
}

// 라디오 기반 선택 카드: 방향키 이동·스크린리더 선택 상태는 네이티브 라디오가 처리한다
export default function OptionGroup<T extends string>({ legend, name, options, value, onChange, disabled=false }: Props<T>) {
  return (
    <fieldset className="option-group" disabled={disabled}>
      <legend className="group-label">{legend}</legend>
      <div className="options">
        {options.map((o) => (
          <label key={o.value} className={o.value === value ? 'option selected' : 'option'}>
            <input
              type="radio"
              className="visually-hidden"
              name={name}
              value={o.value}
              checked={o.value === value}
              onChange={() => onChange(o.value)}
            />
            <span className="option-check" aria-hidden="true" />
            <span className="option-text">
              <span className="option-label">{o.label}</span>
              {o.desc && <span className="option-desc">{o.desc}</span>}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}
