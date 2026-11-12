import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider, useQuery } from '@tanstack/react-query'
import 'pretendard/dist/web/variable/pretendardvariable.css'
import '../index.css'
import { queryClient } from '../api/queryClient'
import DerivedArtifactPanel from '../components/DerivedArtifactPanel'
import type { AdCopy } from '../types/textSchema'

type Manifest = {provenance: 'OFFLINE_FIXTURE'; provider_calls: 0; jobs: {
  job_id: string; mode: 'composed' | 'freeform'; target: {width: number; height: number}; approved_copy: AdCopy
}[]}

export default function DerivedQa() {
  const query = useQuery({queryKey: ['derived-qa-manifest'], retry: false, queryFn: async () => {
    const response = await fetch('/__derived_qa__/manifest')
    if (!response.ok) throw Error('독립된 로컬 QA 서버를 시작해 주세요.')
    const manifest: Manifest = await response.json()
    if (manifest.provenance !== 'OFFLINE_FIXTURE' || manifest.provider_calls !== 0) throw Error('QA 근거 구분이 올바르지 않습니다.')
    return manifest
  }})
  return <main className="derived-qa-page stack">
    <header className="stack"><p className="notice notice-warning"><strong>OFFLINE_FIXTURE · 비과금 브라우저 QA</strong><br />
      가상 제품·가상 카피·로컬 합성입니다. 실제 모델 결과나 사람의 제품 인수를 의미하지 않습니다. 운영 SSO·GCP·Provider는 사용하지 않습니다.</p>
      <h1>원본 제품 보호 시안 검수·저장 QA</h1>
      <p>이 화면의 라벨 확인 체크는 가상 제품에 대한 테스트 입력입니다. 아나비오스 라벨 Ground Truth와 V01은 계속 HOLD입니다.</p>
      <nav className="button-row" aria-label="시안 바로 가기"><a href="#qa-composed">합성형 보호 시안</a><a href="#qa-freeform">자유형 Hybrid 시안</a></nav>
    </header>
    {query.isError && <p role="alert">{query.error.message}</p>}
    {query.isPending && <p role="status">격리 QA Job 확인 중…</p>}
    <div className="dual-grid">{query.data?.jobs.map(job => <article className="card stack" id={`qa-${job.mode}`} tabIndex={-1} key={job.job_id}>
      <h2>{job.mode === 'composed' ? '합성형' : '자유형 + Protected Product Hybrid'}</h2>
      <details><summary>가상 승인 카피 보기</summary><dl><dt>헤드라인</dt><dd>{job.approved_copy.headline}</dd>
        <dt>서브</dt><dd>{job.approved_copy.subline}</dd><dt>CTA</dt><dd>{job.approved_copy.cta}</dd></dl></details>
      <DerivedArtifactPanel jobId={job.job_id} approvedCopy={job.approved_copy} target={job.target} canMutate />
    </article>)}</div>
  </main>
}

createRoot(document.getElementById('root')!).render(<StrictMode><QueryClientProvider client={queryClient}><DerivedQa /></QueryClientProvider></StrictMode>)
