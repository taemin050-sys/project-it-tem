import { delay, http, HttpResponse } from 'msw'
import { API_BASE_URL } from '../config'
import type { Artifact, ArtifactKind, Asset, Job } from '../types/draft'
import type { ProductInput } from '../types/textSchema'
import { analysis, composeMockSvg, MOCK_IMAGE_URL, mockCopyReview, research, researchWithoutSearch, type CopyVariant } from './sampleResult'

// 통합 계약 v0.2 신규 Wire 제안(ai/*, compose) + 레거시 구현의 assets·approvals·artifacts 동작을 흉내 낸다
const BASE = `${API_BASE_URL}/api/v1/jobs`
const STEP_DELAY_MS = 1200

type Stored = Job & { input: ProductInput }
const jobs = new Map<string, Stored>()
const files = new Map<string, Blob>() // `${jobId}/${assetId 또는 산출물 종류}` → 바이트

// 화면 확인용 분기 (제품명): '비화장품' → 사진 분석 실패, '검색실패' → 검색 없이 진행, '긴카피'·'짧은카피' → 카피 길이 예시.
// 제품 특징에 '재생' → 위반 의심(승인 차단)
const has = (text: string, word: string) => text.replace(/\s/g, '').includes(word)
const variant = ({ product_name, features }: ProductInput): CopyVariant =>
  has(features, '재생') ? 'blocked' : has(product_name, '긴카피') ? 'long' : has(product_name, '짧은카피') ? 'short' : 'default'

const hex = () => crypto.randomUUID().replace(/-/g, '')
const toJob = ({ input: _input, ...job }: Stored): Job => job

function artifact(job: Stored, kind: ArtifactKind, blob: Blob): Artifact {
  files.set(`${job.job_id}/${kind}`, blob)
  return { kind, content_type: blob.type, size_bytes: blob.size, download_url: `/api/v1/jobs/${job.job_id}/artifacts/${kind}` }
}

// 순서가 맞지 않는 요청은 레거시 서버처럼 409로 거절한다
type Update = (job: Stored, body: { approved?: boolean }) => Partial<Job> | Promise<Partial<Job>>
function step(path: string, allowed: (job: Stored, body: { approved?: boolean }) => boolean, update: Update) {
  return http.post(`${BASE}/:jobId/${path}`, async ({ params, request }) => {
    const job = jobs.get(String(params.jobId))
    if (!job) return new HttpResponse(null, { status: 404 })
    const body = request.headers.get('content-type')?.includes('json') ? await request.json() as { approved?: boolean } : {}
    if (!allowed(job, body)) {
      return HttpResponse.json({ detail: { error: 'INVALID_WORKFLOW_STATE', current_status: job.status } }, { status: 409 })
    }
    await delay(STEP_DELAY_MS)
    Object.assign(job, await update(job, body))
    return HttpResponse.json(toJob(job))
  })
}

export const handlers = [
  http.post(BASE, async ({ request }) => {
    const form = await request.formData()
    const input = JSON.parse(String(form.get('product_input_json'))) as ProductInput
    const products = form.getAll('product_images') as File[]
    const references = form.getAll('reference_images') as File[]
    if (products.length < 2 || products.length > 5 || references.length > 5
      || products.length !== input.product_image_count || references.length !== input.reference_image_count) {
      return HttpResponse.json({ detail: 'PRODUCT_INPUT_ASSET_COUNT_MISMATCH' }, { status: 422 })
    }
    await delay(500)
    const jobId = hex()
    const assets: Asset[] = [...products.map((f) => ['product', f] as const), ...references.map((f) => ['reference', f] as const)]
      .map(([role, f]) => {
        const asset_id = hex()
        files.set(`${jobId}/${asset_id}`, f)
        return { asset_id, role, original_filename: f.name, content_type: f.type, size_bytes: f.size, width: 0, height: 0, sha256: '' }
      })
    const job: Stored = { job_id: jobId, status: 'INPUTS_VALIDATED', assets, input }
    jobs.set(jobId, job)
    return HttpResponse.json(toJob(job), { status: 201 })
  }),
  http.get(`${BASE}/:jobId`, ({ params }) => {
    const job = jobs.get(String(params.jobId))
    return job ? HttpResponse.json(toJob(job)) : new HttpResponse(null, { status: 404 })
  }),
  http.get(`${BASE}/:jobId/assets/:id`, ({ params }) => serve(`${params.jobId}/${params.id}`)),
  http.get(`${BASE}/:jobId/artifacts/:id`, ({ params }) => serve(`${params.jobId}/${params.id}`)),
  step('ai/analyze', (j) => j.status === 'INPUTS_VALIDATED' && !j.product_analysis, (j) => ({
    product_analysis: { ...analysis, is_cosmetic: !has(j.input.product_name, '비화장품') },
  })),
  step('ai/research', (j) => j.product_analysis?.is_cosmetic === true && !j.research_result, (j) => ({
    research_result: has(j.input.product_name, '검색실패') ? researchWithoutSearch : research,
  })),
  step('ai/copy-review', (j) => j.research_result !== undefined && j.status === 'INPUTS_VALIDATED', (j) => {
    const { copy, report } = mockCopyReview(variant(j.input))
    return { status: 'COPY_REVIEW_REQUIRED', copy_output: copy, compliance_report: report }
  }),
  // 위반 의심이 있으면 서버도 승인을 거절해야 한다 (화면 버튼만으로 막지 않음). 거절은 언제나 가능
  step('approvals/copy', (j, b) => j.status === 'COPY_REVIEW_REQUIRED' && (b.approved === false || j.compliance_report?.passed === true),
    (_, b) => ({ status: b.approved ? 'COPY_APPROVED' : 'COPY_REJECTED' })),
  step('ai/image', (j) => j.status === 'COPY_APPROVED', async (j) => {
    files.set(`${j.job_id}/generated`, await (await fetch(MOCK_IMAGE_URL)).blob())
    return { status: 'IMAGE_REVIEW_REQUIRED', image_candidate: { asset_id: 'generated', preservation_review: 'pending' } }
  }),
  step('approvals/image', (j) => j.status === 'IMAGE_REVIEW_REQUIRED', (_, b) => ({ status: b.approved ? 'IMAGE_APPROVED' : 'IMAGE_REJECTED' })),
  step('compose', (j) => j.status === 'IMAGE_APPROVED', async (j) => {
    const copy = j.copy_output!
    const base = await files.get(`${j.job_id}/generated`)!.text()
    return {
      status: 'COMPLETED',
      artifacts: {
        final: artifact(j, 'final', new Blob([composeMockSvg(base, copy.ad_copy)], { type: 'image/svg+xml' })),
        caption: artifact(j, 'caption', new Blob([`${copy.caption}\n\n${copy.hashtags.join(' ')}\n`], { type: 'text/plain;charset=utf-8' })),
      },
    }
  }),
]

function serve(key: string) {
  const blob = files.get(key)
  return blob ? new HttpResponse(blob, { headers: { 'Content-Type': blob.type } }) : new HttpResponse(null, { status: 404 })
}
