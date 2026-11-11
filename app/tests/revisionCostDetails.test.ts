import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import ts from 'typescript'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const require = createRequire(import.meta.url)
const source = readFileSync(fileURLToPath(new URL('../src/components/RevisionCostDetails.tsx', import.meta.url)), 'utf8')
const compiled = ts.transpileModule(source, {compilerOptions: {jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS}}).outputText
const module = {exports: {} as {default: (props: unknown) => ReturnType<typeof createElement>}}
new Function('module', 'exports', 'require', compiled)(module, module.exports, require)
const Component = module.exports.default
const render = (cost: unknown, revisionId?: string) => renderToStaticMarkup(createElement(Component, {cost, revisionId}))

const fixture = {
  provider_attempt_count: 2, status: 'UNPRICED', actual_usd: null, classification_status: 'COMPLETE',
  attempts: [], revisions: [
    {revision_id: 'image', kind: 'image_correction', state: 'REVIEW_REQUIRED', provider_attempt_count: 1, status: 'UNPRICED', actual_usd: null,
      attempts: [{attempt_id: 'a'.repeat(32), stage: 'image', state: 'SUCCEEDED_USAGE_UNPRICED', model: 'fixture-image',
        usage: {input_tokens: 1200, output_tokens: 300, total_tokens: 1500}, billing_unknown: false, actual_usd: null}]},
    {revision_id: 'copy', kind: 'composed_copy_edit', state: 'COPY_REVIEW_REQUIRED', provider_attempt_count: 1, status: 'UNPRICED', actual_usd: null,
      attempts: [{attempt_id: 'b'.repeat(32), stage: 'copy_review', state: 'SUCCEEDED_USAGE_UNPRICED', model: 'fixture-text',
        usage: {input_tokens: 20, output_tokens: 10, total_tokens: 30}, billing_unknown: false, actual_usd: null}]},
  ],
}

test('Revision usage names image edit and LLM review separately and never invents USD', () => {
  const html = render(fixture)
  assert.match(html, /자유형 오타 수정/)
  assert.match(html, /합성형 문구 수정/)
  assert.match(html, /1,500/)
  assert.match(html, /USD_UNRECONCILED/)
  assert.match(html, /중복으로 더하지 않습니다/)
  assert.doesNotMatch(html, /\$0|0 USD|실제 청구액[^<]*0/)
})

test('A revision card shows its own usage without counting the other revision again', () => {
  const html = render(fixture, 'copy')
  assert.match(html, /모델 호출 1회/)
  assert.match(html, /fixture-text/)
  assert.doesNotMatch(html, /fixture-image|1,500/)
})

test('Unknown or unfinished cost binding stays visible and never suggests automatic retries', () => {
  const cost = structuredClone(fixture)
  cost.classification_status = 'PENDING_LEDGER_BINDING'
  cost.revisions[0].status = 'BILLING_UNKNOWN'
  cost.revisions[0].attempts[0].state = 'BILLING_UNKNOWN'
  cost.revisions[0].attempts[0].billing_unknown = true
  const html = render(cost)
  assert.match(html, /원장 결속을 확인 중/)
  assert.match(html, /과금 미확정/)
  assert.match(html, /자동 재호출 차단/)
})
