import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import ts from 'typescript'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const require = createRequire(import.meta.url)
const source = readFileSync(fileURLToPath(new URL('../src/components/RevisionResultLinks.tsx', import.meta.url)), 'utf8')
const compiled = ts.transpileModule(source, {compilerOptions: {jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS}}).outputText
const module = {exports: {} as {default: (props: unknown) => ReturnType<typeof createElement>}}
new Function('module', 'exports', 'require', compiled)(module, module.exports, require)
const Component = module.exports.default
const render = (composed: boolean, freeform: boolean) => renderToStaticMarkup(createElement(Component, {completed: {composed, freeform}}))

test('Unapproved revisions do not create a final-download shortcut', () => {
  assert.equal(render(false, false), '')
})

test('A completed composed revision is discoverable without promoting the rejected freeform', () => {
  const html = render(true, false)
  assert.match(html, /승인된 수정본 1개/)
  assert.match(html, /href="#result-revisions-composed"/)
  assert.doesNotMatch(html, /href="#result-revisions-freeform"/)
  assert.match(html, /원본 시안의 검토·거절 상태는 그대로 유지/)
})

test('Both independently completed revisions have their own download destinations', () => {
  const html = render(true, true)
  assert.match(html, /승인된 수정본 2개/)
  assert.match(html, /href="#result-revisions-composed"/)
  assert.match(html, /href="#result-revisions-freeform"/)
})
