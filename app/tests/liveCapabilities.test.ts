import assert from 'node:assert/strict'
import test from 'node:test'
import { checkedLiveCapabilities, requireLiveDualRatio, supportedLiveDualRatios } from '../src/api/liveCapabilities.ts'
import { checkedDualSnapshotRatio } from '../src/api/dualArtifacts.ts'

const ready = {live_enabled: true, live_dual_enabled: true, live_dual_configured: true}

test('historical capability without ratio fields admits only 4:5', () => {
  const caps = checkedLiveCapabilities(ready)
  assert.deepEqual(supportedLiveDualRatios(caps), ['4:5'])
  assert.doesNotThrow(() => requireLiveDualRatio(caps, '4:5'))
  for (const ratio of ['3:4', '9:16']) assert.throws(() => requireLiveDualRatio(caps, ratio))
})

test('server capability and explicit image CTA unlock all three Dual ratios', () => {
  const caps = checkedLiveCapabilities({...ready, supported_ratios: ['4:5', '3:4', '9:16'], cta_policy_9x16: 'IMAGE_CTA_BOTH'})
  assert.deepEqual(supportedLiveDualRatios(caps), ['3:4', '4:5', '9:16'])
  for (const ratio of ['3:4', '4:5', '9:16']) assert.doesNotThrow(() => requireLiveDualRatio(caps, ratio))
})

test('9:16 remains held when its CTA answer is absent or null despite advertised support', () => {
  for (const policy of [{}, {cta_policy_9x16: null}]) {
    const caps = checkedLiveCapabilities({...ready, supported_ratios: ['3:4', '4:5', '9:16'], ...policy})
    assert.deepEqual(supportedLiveDualRatios(caps), ['3:4', '4:5'])
    assert.throws(() => requireLiveDualRatio(caps, '9:16'))
  }
})

test('CTA confirmation alone never enables a ratio the server did not advertise', () => {
  const caps = checkedLiveCapabilities({...ready, supported_ratios: ['4:5'], cta_policy_9x16: 'IMAGE_CTA_BOTH'})
  assert.deepEqual(supportedLiveDualRatios(caps), ['4:5'])
  assert.throws(() => requireLiveDualRatio(caps, '9:16'))
})

test('stopped Dual execution and an empty advertised list cannot start a paid request', () => {
  const paused = checkedLiveCapabilities({...ready, live_dual_enabled: false, supported_ratios: ['3:4', '4:5']})
  assert.deepEqual(supportedLiveDualRatios(paused), ['3:4', '4:5'])
  assert.throws(() => requireLiveDualRatio(paused, '4:5'))
  const empty = checkedLiveCapabilities({...ready, supported_ratios: []})
  assert.deepEqual(supportedLiveDualRatios(empty), [])
  assert.throws(() => requireLiveDualRatio(empty, '4:5'))
  assert.deepEqual(supportedLiveDualRatios(undefined), [])
})

test('malformed API ratio and authority data fail closed rather than enabling a subset', () => {
  for (const changed of [
    {supported_ratios: ['4:5', '1:1']}, {supported_ratios: ['4:5', '4:5']},
    {supported_ratios: '3:4'}, {supported_ratios: null}, {supported_ratios: [true]},
    {live_enabled: 'true'}, {live_dual_enabled: 1}, {live_dual_configured: 'YES'},
    {cta_policy_9x16: 'PLATFORM_CTA'}, {cta_policy_9x16: true},
  ]) assert.throws(() => checkedLiveCapabilities({...ready, ...changed}))
  for (const value of [null, [], 'ready', true, {}]) assert.throws(() => checkedLiveCapabilities(value))
})

test('restored or forged ratio values are rejected at the input guard', () => {
  const caps = checkedLiveCapabilities({...ready, supported_ratios: ['3:4', '4:5', '9:16'], cta_policy_9x16: 'IMAGE_CTA_BOTH'})
  for (const ratio of ['1:1', '9:16 ', 916, null, ['4:5'], {ratio: '4:5'}]) {
    assert.throws(() => requireLiveDualRatio(caps, ratio))
  }
})

test('malicious Dual output metadata fails before indexing a rendering profile', () => {
  for (const ratio of ['3:4', '4:5', '9:16']) assert.equal(checkedDualSnapshotRatio({image_size: ratio}).image_size, ratio)
  for (const ratio of ['1:1', undefined, null, 'constructor', ['4:5'], {toString: () => '4:5'}]) {
    assert.throws(() => checkedDualSnapshotRatio({image_size: ratio}))
  }
})
