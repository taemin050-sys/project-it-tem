import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { adExamples, MOCK_IMAGE_URLS } from '../src/mocks/sampleResult.ts'

test('landing preview embeds exact Owner SVGs without additional image HTTP requests', () => {
  const expected = ['ad_moss.svg', 'ad_beige.svg', 'ad_tile.svg']
  assert.equal(adExamples.length, expected.length)
  for (const [i, file] of expected.entries()) {
    const embedded = adExamples[i].imageUrl
    assert.ok(embedded.startsWith('data:image/svg+xml;charset=utf-8,'))
    const raw = decodeURIComponent(embedded.slice(embedded.indexOf(',') + 1))
    const original = readFileSync(fileURLToPath(new URL('../public/mock/' + file, import.meta.url)), 'utf8')
    assert.equal(raw, original)
  }
  assert.ok(MOCK_IMAGE_URLS.every(url => url.startsWith('/mock/')), 'existing fixture paths must stay unchanged')
})
