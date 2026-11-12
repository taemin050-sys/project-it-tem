import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { STEPS, stepIndex } from '../steps'
import { QA_OFFLINE_FIXTURE } from '../config'

type Props = {
  title: string
  description?: ReactNode
  /** 이미지 시안처럼 결과물이 큰 화면은 넓게 */
  wide?: boolean
  back?: { to: string; label: string }
  /** 하단 작업 영역 오른쪽 (다음 단계·주요 작업 버튼) */
  actions?: ReactNode
  /** 하단 작업 영역 위에 붙는 상태·오류 문구 */
  actionsNote?: ReactNode
  /** 결과 파일을 읽는 화면은 작업 영역을 문서 흐름에 둔다 */
  stickyActions?: boolean
  children: ReactNode
}

const pad = (n: number) => String(n).padStart(2, '0')

// 모든 단계가 같은 제목 위계와 하단 이전/다음 버튼 위치를 쓰도록 하는 틀
export default function StepPage({ title, description, wide, back, actions, actionsNote, stickyActions = true, children }: Props) {
  const index = stepIndex(useLocation().pathname)
  const width = wide ? 'step-width wide' : 'step-width'

  return (
    <>
      <div className={`step-page ${width}`}>
        <header className="step-head">
          {index >= 0 && <p className="eyebrow">Step {pad(index + 1)} / {pad(STEPS.length)}</p>}
          <h1>{title}</h1>
          {description && <p className="step-desc">{description}</p>}
        </header>
        {QA_OFFLINE_FIXTURE && <div className="notice notice-warning" role="status" data-testid="qa-fixture-banner">
          <p className="notice-title">QA 전용 OFFLINE_FIXTURE · 실제 AI 생성 아님</p>
          <p>제품 분석·카피·이미지는 저장된 시험 데이터이며, 모델 비용·속도·제품 보존 품질을 검증한 결과가 아닙니다.</p>
        </div>}
        {children}
      </div>
      <div className={`step-actions${stickyActions ? '' : ' in-flow'}`}>
        <div className={width}>
          {actionsNote && <div className="step-actions-note">{actionsNote}</div>}
          <div className="step-actions-row">
            {back
              ? <Link className="button secondary" to={back.to}><span aria-hidden="true">←</span> {back.label}</Link>
              : <span />}
            {actions}
          </div>
        </div>
      </div>
    </>
  )
}
