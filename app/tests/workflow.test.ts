import assert from 'node:assert/strict'
import { test } from 'node:test'
import { canApproveCopy, imagePath, isMockJob, nextStep } from '../src/lib/pipeline.ts'
import { validateProduct } from '../src/lib/validateProduct.ts'
import { analysis, mockCopyReview, research } from '../src/mocks/sampleResult.ts'
import type { ProductForm } from '../src/store/projectStore.ts'
import type { Job } from '../src/types/draft.ts'

const accept = ['image/png']
const limits = { product: { minFiles: 2, maxFiles: 5, acceptTypes: accept }, reference: { minFiles: 0, maxFiles: 5, acceptTypes: accept } }
const png = new File([new Uint8Array(1)], 'a.png', { type: 'image/png' })
const base: ProductForm = {
  brand_name: null, product_name: '글로우 세럼', product_category: null, features: '가벼운 보습 세럼',
  ad_purpose: '신제품 홍보', is_functional: false, photo_verified: true,
}

test('제품 정보 검사: 제품 사진 2장·배경 0장·브랜드/카테고리 없음은 정상', () => {
  assert.deepEqual(validateProduct([png, png], [], base, limits), {})
})

test('제품 정보 검사: 누락 항목마다 해당 필드에 오류', () => {
  const errors = validateProduct([png], Array(6).fill(png), { ...base, product_name: ' ', features: '', photo_verified: false }, limits)
  assert.deepEqual(Object.keys(errors).sort(), ['features', 'images', 'photo_verified', 'product_name', 'references'])
})

const job = (patch: Partial<Job>): Job => ({ job_id: 'j', status: 'INPUTS_VALIDATED', ...patch })

test('단계 진행(v2 제안): 분석 → 조사 → 카피·검수, 사용자 승인 전에는 멈춤', () => {
  assert.equal(nextStep(job({}), 'v2'), 'ai/analyze')
  assert.equal(nextStep(job({ product_analysis: analysis }), 'v2'), 'ai/research')
  assert.equal(nextStep(job({ product_analysis: analysis, research_result: research }), 'v2'), 'ai/copy-review')
  assert.equal(nextStep(job({ status: 'COPY_REVIEW_REQUIRED' }), 'v2'), null)
  assert.equal(nextStep(job({ status: 'COPY_APPROVED' }), 'v2'), 'ai/image')
  assert.equal(nextStep(job({ status: 'IMAGE_REVIEW_REQUIRED' }), 'v2'), null)
  assert.equal(nextStep(job({ status: 'IMAGE_APPROVED' }), 'v2'), 'compose')
  assert.equal(nextStep(job({ status: 'COMPLETED' }), 'v2'), null)
})

test('단계 진행(v2 제안): 화장품이 아니면 이후 유료 단계를 보내지 않는다', () => {
  assert.equal(nextStep(job({ product_analysis: { ...analysis, is_cosmetic: false } }), 'v2'), null)
})

test('단계 진행(레거시 구현): mock/plan → mock/copy → 승인 → mock/image → 승인 → mock/compose, 거절은 종료', () => {
  const order = (['INPUTS_VALIDATED', 'PLAN_READY', 'COPY_REVIEW_REQUIRED', 'COPY_APPROVED', 'IMAGE_REVIEW_REQUIRED', 'IMAGE_APPROVED', 'COMPLETED', 'COPY_REJECTED', 'IMAGE_REJECTED'] as const)
    .map((status) => nextStep(job({ status }), 'legacy'))
  assert.deepEqual(order, ['mock/plan', 'mock/copy', null, 'mock/image', null, 'mock/compose', null, null, null])
})

test('카피 승인: 검수 통과만, 위반 의심·검수 없음은 불가, 리포트 없는 레거시 mock 문구만 예외', () => {
  const review = 'COPY_REVIEW_REQUIRED' as const
  assert.equal(canApproveCopy(job({ status: review, compliance_report: mockCopyReview('default').report })), true)
  assert.equal(canApproveCopy(job({ status: review, compliance_report: mockCopyReview('blocked').report })), false)
  assert.equal(canApproveCopy(job({ status: review })), false)
  assert.equal(canApproveCopy(job({ status: review, copy_candidate: { mock: false, text: 'x', compliance_checked: false, disclaimer: '' } })), false)
  assert.equal(canApproveCopy(job({ status: review, copy_candidate: { mock: true, text: 'x', compliance_checked: false, disclaimer: '' } })), true)
  assert.equal(canApproveCopy(job({ status: 'COPY_APPROVED', compliance_report: mockCopyReview('default').report })), false)
})

test('이미지 경로·mock 표시: v2는 Asset, 레거시는 image 산출물', () => {
  assert.equal(imagePath(job({ image_candidate: { asset_id: 'a1' } })), '/api/v1/jobs/j/assets/a1')
  const legacyImage = { kind: 'image' as const, content_type: 'image/png', size_bytes: 1, download_url: '/api/v1/jobs/j/artifacts/image' }
  assert.equal(imagePath(job({ image_candidate: { mock: true }, artifacts: { image: legacyImage } })), '/api/v1/jobs/j/artifacts/image')
  assert.equal(isMockJob(job({ image_candidate: { mock: true } })), true)
  assert.equal(isMockJob(job({ image_candidate: { asset_id: 'a1' } })), false)
})
