import assert from 'node:assert/strict'
import { test } from 'node:test'
import { formatSharedAtKST } from '../src/demo/sharedTime.ts'

test('09:16:05 UTC is 18:16:05 KST (not the raw UTC time)', () => {
  const result = formatSharedAtKST('2026-11-03T09:16:05Z')
  assert.match(result, /2026/)
  assert.match(result, /18:16:05 KST/)
  assert.doesNotMatch(result, /09:16:05 KST/)
})
test('UTC day boundary and ISO Z vs +00:00 represent the same instant', () => {
  const a = formatSharedAtKST('2026-11-03T15:30:00Z')
  assert.match(a, /2026/)
  assert.match(a, /11/)
  assert.match(a, /04/)
  assert.match(a, /00:30:00 KST/)
  assert.equal(formatSharedAtKST('2026-11-03T09:16:05Z'),
    formatSharedAtKST('2026-11-03T09:16:05+00:00'))
})
test('invalid, unknown-origin, or non-UTC inputs are never guessed', () => {
  for (const input of [null, undefined, '', 'not-a-date', '2026-02-30T09:16:05Z',
    '2026-11-03 09:16:05', '2026-11-03T09:16:05+09:00',
    '2026-11-03T09:16:05', '2026-11-03T25:16:05Z']) {
    assert.equal(formatSharedAtKST(input), '공유 시각 확인 불가')
  }
})
test('explicit KST formatting does not depend on system timezone or add +9 twice', () => {
  const saved = process.env.TZ
  try {
    for (const zone of ['UTC', 'Asia/Seoul', 'America/Los_Angeles', 'Europe/Paris']) {
      process.env.TZ = zone
      assert.match(formatSharedAtKST('2026-11-03T09:16:05Z'), /18:16:05 KST/)
    }
  } finally {
    if (saved === undefined) delete process.env.TZ
    else process.env.TZ = saved
  }
})
