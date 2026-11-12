import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { test } from 'node:test'
import ts from 'typescript'

// FE Owner A v1 is immutable: an intentional A v2 must use a NEW version.
const PINNED_OWNER_A_V1_SHA = 'c9fe0d76a35e8171cbfca2b23ae1eafc2bd4d60e9ad7cb8164098b6f420d43e1'
const read = (path: string) => readFileSync(new URL('../src/' + path, import.meta.url), 'utf8')
const canonical = (v: unknown): unknown => {
  if (Array.isArray(v)) return v.map(canonical)
  if (v !== null && typeof v === 'object')
    return Object.fromEntries(Object.entries(v).sort(([a], [b]) => a.localeCompare(b))
      .map(([k, value]) => [k, canonical(value)]))
  return v
}

test('FE AD_LAYOUT matches frozen Image Owner A v1 canonical SHA-256', () => {
  const config = read('config.ts')
  const start = config.indexOf('const A_REGION')
  const end = config.indexOf('// Explicit build-time QA label only.')
  assert.ok(start >= 0 && end > start, 'FE Owner layout must remain exported')
  const snippet = config.slice(start, end)
  const js = ts.transpileModule(snippet, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText
  const sandbox: { exports: Record<string, unknown> } = { exports: {} }
  runInNewContext(js, sandbox, { timeout: 1000 })
  const layout = JSON.parse(JSON.stringify(sandbox.exports.AD_LAYOUT))
  const sha = createHash('sha256').update(JSON.stringify(canonical(layout))).digest('hex')
  assert.equal(sha, PINNED_OWNER_A_V1_SHA)
  assert.deepEqual(layout.protected_regions, [], 'unverified product bounds must never be fabricated')
})

test('live and diagnostic A composition send FE Owner layout; legacy stays separate', () => {
  const flow = read('api/liveFlow.ts')
  const demo = read('demo/DemoLiveConsole.tsx')
  assert.match(flow, /template_profile==='A_CENTERED'\?AD_LAYOUT:LEGACY_LAYOUT/)
  assert.match(demo, /template_profile==='A_CENTERED'\?\{layout:AD_LAYOUT\}:\{layout:LEGACY_LAYOUT\}/)
  assert.match(flow, /retryCompose=\(id:string\)=>retryApprovedComposition\(id\)/)
  assert.match(flow, /IMAGE_APPROVAL_STALE_OR_COMPLETED/)
})

test('FE consumer UI does not reintroduce internal status or provider ledger', () => {
  const copy = read('pages/CopyPage.tsx')
  const exp = read('pages/ExportPage.tsx')
  assert.doesNotMatch(copy, /실제 AI 작업:/)
  assert.match(copy, /BILLING_UNKNOWN/)
  assert.doesNotMatch(exp, /실제 AI 실행 기록|getLivePerformance|provider_attempts/)
  assert.match(exp, /합성만 다시 시도/)
  assert.match(exp, /수동 검토 필요/)
})
