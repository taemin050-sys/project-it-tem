import type { Ratio } from '../config'

export type LiveCapabilities = {
  live_enabled: boolean
  live_dual_enabled?: boolean
  live_dual_configured?: boolean
  reason?: string | null
  source_sha?: string
  supported_ratios?: Ratio[]
  cta_policy_9x16?: 'IMAGE_CTA_BOTH' | null
}

const RATIOS = ['3:4', '4:5', '9:16'] as const
const knownRatio = (value: unknown): value is Ratio => RATIOS.some(ratio => ratio === value)

/** Treat capability JSON as untrusted input before it enables a paid flow. */
export function checkedLiveCapabilities(value: unknown): LiveCapabilities {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('서버의 생성 지원 정보를 확인하지 못했습니다.')
  const row = value as Record<string, unknown>
  if (typeof row.live_enabled !== 'boolean' ||
      ['live_dual_enabled', 'live_dual_configured'].some(key => row[key] !== undefined && typeof row[key] !== 'boolean') ||
      (row.reason !== undefined && row.reason !== null && typeof row.reason !== 'string') ||
      (row.source_sha !== undefined && typeof row.source_sha !== 'string') ||
      (row.cta_policy_9x16 !== undefined && row.cta_policy_9x16 !== null && row.cta_policy_9x16 !== 'IMAGE_CTA_BOTH')) {
    throw Error('서버의 생성 지원 정보를 확인하지 못했습니다.')
  }
  if (row.supported_ratios !== undefined && (!Array.isArray(row.supported_ratios) ||
      row.supported_ratios.length > RATIOS.length || !row.supported_ratios.every(knownRatio) ||
      new Set(row.supported_ratios).size !== row.supported_ratios.length)) {
    throw Error('서버의 지원 비율을 확인하지 못했습니다.')
  }
  return row as LiveCapabilities
}

/** A missing field is the historical 4:5 contract, never implied multi-ratio. */
export function supportedLiveDualRatios(capabilities: LiveCapabilities | undefined): readonly Ratio[] {
  if (!capabilities) return []
  const ratios = capabilities.supported_ratios ?? ['4:5']
  return RATIOS.filter(ratio => ratios.includes(ratio) &&
    (ratio !== '9:16' || capabilities.cta_policy_9x16 === 'IMAGE_CTA_BOTH'))
}

export function requireLiveDualRatio(capabilities: LiveCapabilities, ratio: unknown): asserts ratio is Ratio {
  if (!knownRatio(ratio) || !supportedLiveDualRatios(capabilities).includes(ratio)) {
    throw Error(ratio === '9:16'
      ? '9:16의 서버 지원과 두 시안의 이미지 CTA 정책을 확인한 후 시작할 수 있습니다.'
      : '선택한 비율의 서버 지원을 확인한 후 시작할 수 있습니다.')
  }
  if (capabilities.live_dual_enabled !== true) throw Error('두 시안 실행 준비를 확인하고 있습니다. 준비가 완료되면 시작할 수 있습니다.')
}
