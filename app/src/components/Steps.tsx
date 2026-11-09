import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { STEPS, stepIndex } from '../steps'
import Icon from './Icon'

type State = 'done' | 'current' | 'todo'

// 지나온 단계만 되돌아갈 수 있고, 다음 단계는 각 화면의 버튼으로만 넘어간다
function useSteps() {
  const current = stepIndex(useLocation().pathname)
  return STEPS.map((s, i) => ({ ...s, i, state: (i < current ? 'done' : i === current ? 'current' : 'todo') as State }))
}

function StepLink({ to, state, className, children }: { to: string; state: State; className: string; children: ReactNode }) {
  return state === 'done'
    ? <Link to={to} className={className}>{children}</Link>
    : <span className={className} aria-current={state === 'current' ? 'step' : undefined}>{children}</span>
}

// 1단계 시안: 알약
const PILL_LABELS = ['제품 정보 입력', '기획·카피 검토', '이미지 검토', '최종 결과']
export function StepPills() {
  return (
    <ol className="pills" aria-label="광고 만들기 진행 단계">
      {useSteps().map((s) => (
        <li key={s.path}>
          <StepLink to={s.path} state={s.state} className={`pill is-${s.state}`}>
            <span className="pill-no">{s.state === 'done' ? <Icon name="check" className="label-sm" /> : s.i + 1}</span>
            <span>{PILL_LABELS[s.i]}</span>
            {s.state === 'current' && <span className="ping" aria-hidden="true" />}
          </StepLink>
        </li>
      ))}
    </ol>
  )
}

// 2단계 시안: 카드
const CARD_LABELS = ['제품 정보 입력', '기획·카피 검토', '인스타 비주얼 검토', '최종 소재 배포']
export function StepCards() {
  return (
    <ol className="stepcards" aria-label="광고 만들기 진행 단계">
      {useSteps().map((s) => (
        <li key={s.path}>
          <StepLink to={s.path} state={s.state} className={`stepcard is-${s.state}`}>
            <span className="stepcard-no">
              {s.state === 'done' ? <Icon name="check" /> : s.state === 'current' ? <Icon name="edit_note" fill /> : s.i + 1}
            </span>
            <span style={{ minWidth: 0 }}>
              <small>STEP 0{s.i + 1}{s.state === 'current' && ' · 진행중'}</small>
              <b>{CARD_LABELS[s.i]}</b>
            </span>
            {s.state === 'current' && <span className="live-dot" aria-hidden="true" />}
          </StepLink>
        </li>
      ))}
    </ol>
  )
}

// 3단계 시안: 막대
const BAR_LABELS = ['제품 정보 입력', '기획·카피 검토', '이미지 검토', '최종 소재 배포']
const BAR_STATE = { done: '완료', current: 'Active', todo: '대기' }
const BAR_ICON = { done: 'check_circle', current: 'sync', todo: 'circle' }
export function StepBars() {
  return (
    <ol className="stepbars" aria-label="광고 만들기 진행 단계">
      {useSteps().map((s) => (
        <li key={s.path} className={`stepbar is-${s.state}`}>
          <StepLink to={s.path} state={s.state} className="stepbar-row">
            <span><Icon name={BAR_ICON[s.state]} /> {s.i + 1}. {BAR_LABELS[s.i]}{s.state === 'current' && ' (현재)'}</span>
            <small>{BAR_STATE[s.state]}</small>
          </StepLink>
          <div className="stepbar-track" />
        </li>
      ))}
    </ol>
  )
}

// 4단계 시안: 체크
const CHECK_LABELS = ['제품 정보 입력', '기획·카피 검토', '인스타 비주얼 승인', '최종 결과 완성! 🎉']
export function StepChecks({ finished }: { finished: boolean }) {
  return (
    <ol className="stepchecks" aria-label="광고 만들기 진행 단계">
      {useSteps().map((s) => (
        <li key={s.path}>
          <StepLink to={s.path} state={s.state} className={`stepcheck is-${s.state}`}>
            <span className="stepcheck-dot"><Icon name={s.state === 'current' ? 'done_all' : 'check'} /></span>
            <span>
              <small>{s.state === 'current' ? 'Step 4 Final' : `${s.i + 1}단계 완료`}</small>
              <b>{s.state === 'current' && !finished ? STEPS[s.i].label : CHECK_LABELS[s.i]}</b>
            </span>
          </StepLink>
        </li>
      ))}
    </ol>
  )
}
