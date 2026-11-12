import assert from 'node:assert/strict'
import test from 'node:test'
import {
  belongsToDerivedContext, canRevokeDerivedAdmission, checkedDerivedSnapshot, derivedArtifactPath, derivedFinalizeReady,
  derivedModeLabel, derivedPath, derivedProposalReady, derivedReviewReady,
  parseDerivedGeometry, type DerivedRender, type DerivedSnapshot, type DerivedVisualReview,
} from '../src/api/derivedContract.ts'
import { sendDerivedAdmissionRevocation } from '../src/api/derivedRevocation.ts'

const sha = (letter: string) => letter.repeat(64)
const copy = {headline: '매일의 샴푸 시간', subline: '차분하게 씻어내는', cta: '일상을 만나보세요'}
function render(): DerivedRender {
  return {derived_id: 'derived-a', job_id: 'job/a', render_mode: 'freeform_protected_product_hybrid',
    state: 'REVIEW_REQUIRED', revision: 3, recipe_sha: sha('a'), context_sha: sha('b'),
    admission_sha: sha('c'), preview_sha: sha('d'), approval_sha: null, final_sha: null,
    caption_sha: null, receipt_sha: null, output_size: {width: 1080, height: 1350}, artifacts: {}, hold_code: null}
}
function snapshot(): DerivedSnapshot {
  return {job_id: 'job/a', available: true, can_admit: true, can_review: true, context_sha: sha('b'),
    revision: 2, hold_code: null, proposals: [{proposal_id: 'proposal-a', title: '제품 보존',
      render_mode: 'freeform_protected_product_hybrid', recipe_sha: sha('a'), requires_ground_truth: true}],
    renders: [render()], selected_derived_id: null}
}
function review(): DerivedVisualReview {
  return {source_pixels_preserved: true, edges_acceptable: true, no_duplicate_product: true,
    no_ghost_product: true, no_copy_occlusion: true, cta_policy_matches: true,
    label_ground_truth_confirmed: true, mobile_readable: true, observed_copy: {...copy}}
}

test('derived artifact GET binds exact job, derived identity, kind and SHA', () => {
  const candidate = render()
  const expected = `/demo/api/live/jobs/job%2Fa/derived/renders/derived-a/artifacts/preview?sha256=${sha('d')}`
  candidate.artifacts.preview = expected
  assert.equal(derivedPath(candidate.job_id), '/demo/api/live/jobs/job%2Fa/derived')
  assert.equal(derivedArtifactPath(candidate, 'preview'), expected)
  assert.equal(derivedArtifactPath({...candidate, job_id: 'other'}, 'preview'), undefined)
  assert.equal(derivedArtifactPath({...candidate, derived_id: 'other'}, 'preview'), undefined)
  assert.equal(derivedArtifactPath({...candidate, preview_sha: sha('e')}, 'preview'), undefined)
  assert.equal(derivedArtifactPath(candidate, 'final'), undefined)
  candidate.artifacts.preview = `https://unrelated.example${expected}`
  assert.equal(derivedArtifactPath(candidate, 'preview'), undefined)
})

test('raw candidate and pure Freeform artifact URLs are rejected by the derived namespace', () => {
  const candidate = render()
  candidate.artifacts.preview = `/demo/api/live/jobs/job%2Fa/dual/freeform/artifacts/candidate?sha256=${sha('d')}`
  assert.equal(derivedArtifactPath(candidate, 'preview'), undefined)
  assert.equal(derivedModeLabel(candidate.render_mode), '자유형 + 원본 제품 보호 합성')
  assert.equal(derivedModeLabel('composed_protected_product'), '합성형 + 원본 제품 보호')
})

test('independent visual review requires exact observed copy and all human checks', () => {
  const current = snapshot()
  const candidate = render()
  const checks = review()
  assert.equal(derivedReviewReady(current, candidate, checks, copy), true)
  for (const key of ['source_pixels_preserved', 'edges_acceptable', 'no_duplicate_product',
    'no_ghost_product', 'no_copy_occlusion', 'cta_policy_matches', 'label_ground_truth_confirmed',
    'mobile_readable'] as const) {
    assert.equal(derivedReviewReady(current, candidate, {...checks, [key]: false}, copy), false, key)
  }
  assert.equal(derivedReviewReady(current, candidate, {...checks,
    observed_copy: {...copy, headline: `${copy.headline} `}}, copy), false)
  assert.equal(derivedReviewReady(current, candidate, checks, undefined), false)
})

test('stale recipe context, actor capability and visual HOLD prevent approval', () => {
  const current = snapshot()
  assert.equal(derivedReviewReady({...current, can_review: false}, render(), review(), copy), false)
  assert.equal(derivedReviewReady({...current, available: false}, render(), review(), copy), false)
  assert.equal(derivedReviewReady({...current, hold_code: 'BILLING_UNKNOWN'}, render(), review(), copy), false)
  assert.equal(derivedReviewReady(current, {...render(), hold_code: 'LABEL_GROUND_TRUTH_PENDING'}, review(), copy), false)
  assert.equal(derivedReviewReady(current, {...render(), context_sha: sha('e')}, review(), copy), false)
  assert.equal(derivedReviewReady(current, {...render(), job_id: 'other'}, review(), copy), false)
  assert.equal(derivedReviewReady(current, {...render(), state: 'STALE'}, review(), copy), false)
})

test('raw approval does not finalize a derived preview without its separate approval', () => {
  const current = snapshot()
  assert.equal(derivedFinalizeReady(current, render()), false)
  assert.equal(derivedFinalizeReady(current, {...render(), state: 'APPROVED'}), false)
  const approved = {...render(), state: 'APPROVED' as const, approval_sha: sha('f')}
  assert.equal(derivedFinalizeReady(current, approved), true)
  assert.equal(derivedFinalizeReady(current, {...approved, preview_sha: null}), false)
  assert.equal(derivedFinalizeReady(current, {...approved, hold_code: 'VISUAL_HOLD'}), false)
  assert.equal(derivedFinalizeReady({...current, can_review: false}, approved), false)
})

test('recipe proposal requires authenticated server capability and matching current version', () => {
  const current = snapshot()
  const proposal = current.proposals[0]
  assert.equal(derivedProposalReady(current, proposal), true)
  assert.equal(derivedProposalReady({...current, can_admit: false}, proposal), false)
  assert.equal(derivedProposalReady({...current, hold_code: 'UNAVAILABLE'}, proposal), false)
  assert.equal(derivedProposalReady(current, {...proposal, recipe_sha: 'bad'}), false)
  assert.equal(derivedProposalReady(current, {...proposal, hold_code: 'SOURCE_MISSING'}), false)
})

test('unsupported mode and crossed resource response fail closed', () => {
  const current = snapshot()
  assert.equal(checkedDerivedSnapshot(current, 'job/a'), current)
  assert.throws(() => checkedDerivedSnapshot(current, 'another'))
  assert.throws(() => checkedDerivedSnapshot({...current,
    renders: [{...render(), render_mode: 'freeform' as DerivedRender['render_mode']}]}, 'job/a'))
  assert.throws(() => checkedDerivedSnapshot({...current,
    renders: [{...render(), state: 'FUTURE' as DerivedRender['state']}]}, 'job/a'))
  assert.equal(belongsToDerivedContext(current, {...render(), revision: 3.5}), false)
})


test('custom placement allows explicit geometry and rejects paths and noninteger coordinates', () => {
  const geometry = {source_crop: [0, 0, 800, 1000], registered_size: [400, 500],
    output_offset: [300, 350], protected_rois: {label: [200, 200, 400, 400]},
    model_regions: [[300, 300, 800, 1100]], copy_exclusions: [[100, 40, 1000, 240]]}
  assert.deepEqual(parseDerivedGeometry(JSON.stringify(geometry)), geometry)
  assert.throws(() => parseDerivedGeometry(JSON.stringify({...geometry, source_path: '/etc/passwd'})))
  assert.throws(() => parseDerivedGeometry(JSON.stringify({...geometry, output_offset: [-1, 40]})))
  assert.throws(() => parseDerivedGeometry(JSON.stringify({...geometry, registered_size: [400.5, 500]})))
  assert.throws(() => parseDerivedGeometry(JSON.stringify({...geometry, protected_rois: {label: [1, 2]}})))
  assert.throws(() => parseDerivedGeometry(JSON.stringify({...geometry, model_regions: [[1, 2, 3]]})))
  assert.throws(() => parseDerivedGeometry('null'))
  assert.throws(() => parseDerivedGeometry('[]'))
  assert.throws(() => parseDerivedGeometry('broken'))
})

test('a future derived proposal cannot silently acquire a known mode label', () => {
  const current = snapshot()
  assert.throws(() => checkedDerivedSnapshot({...current,
    proposals: [{...current.proposals[0], render_mode: 'future' as DerivedRender['render_mode']}]}, 'job/a'))
})

test('derived admission revocation sends one exact current render/context/admission CAS request', async () => {
  const current = snapshot()
  const candidate = {...render(), state: 'COMPLETED' as const}
  const sent: {path: string; options: {method: string; body: string}}[] = []
  const result = await sendDerivedAdmissionRevocation(current, candidate, async (path, options) => {
    sent.push({path, options})
    return {...candidate, state: 'STALE'}
  })
  assert.equal(result.state, 'STALE')
  assert.equal(sent.length, 1)
  assert.equal(sent[0].path, '/demo/api/live/jobs/job%2Fa/derived/renders/derived-a/revoke-admission')
  assert.equal(sent[0].options.method, 'POST')
  assert.deepEqual(JSON.parse(sent[0].options.body), {expected_revision: 3,
    expected_context_sha: sha('b'), expected_admission_sha: sha('c')})
})

test('revocation requires can_admit and rejects STALE, crossed or malformed current context', () => {
  const current = snapshot()
  const candidate = render()
  assert.equal(canRevokeDerivedAdmission(current, candidate), true)
  for (const [source, value] of [
    [{...current, can_admit: false}, candidate], [{...current, available: false}, candidate],
    [current, {...candidate, state: 'STALE'}], [current, {...candidate, job_id: 'other'}],
    [current, {...candidate, context_sha: sha('e')}], [current, {...candidate, admission_sha: 'bad'}],
    [current, {...candidate, revision: 2.5}],
  ] as [DerivedSnapshot, DerivedRender][]) {
    let calls = 0
    assert.throws(() => sendDerivedAdmissionRevocation(source, value, async () => {calls++; return value}))
    assert.equal(calls, 0)
  }
  // A safety stop remains possible during an unrelated quality/billing HOLD.
  assert.equal(canRevokeDerivedAdmission({...current, hold_code: 'BILLING_UNKNOWN'}, candidate), true)
})

test('lost response or conflict never retries a revocation automatically', async () => {
  for (const message of ['network response lost', '409 stale admission']) {
    let calls = 0
    await assert.rejects(sendDerivedAdmissionRevocation(snapshot(), render(), async () => {
      calls++
      throw Error(message)
    }), {message})
    assert.equal(calls, 1)
  }
})
