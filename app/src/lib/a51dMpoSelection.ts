/** A51D OFFLINE_FIXTURE-only MPO explicit choice. NOT an approved Owner contract.
 *
 * The server is the actor/source/frame authority, not this WeakMap.
 * Selected files stay in RAM; user action must be repeated after reload.
 * Production builds never activate this module absent a test-only feature flag.
 */
import { hasEmbeddedMpoSignature } from './mpo.ts'

export const A51D_MPO_FIXTURE =
  import.meta.env?.VITE_A51D_MPO_FIXTURE_BRIDGE === 'YES'

export type PreviewFrame = {
  index: number
  width: number
  height: number
  preview_png_sha256: string
  preview_data_uri: string
}
export type PreviewReceipt = {
  contract: string
  token: string
  source_sha256: string
  source_frame_count: number
  frames: PreviewFrame[]
  requires_explicit_confirmation: true
  contract_final_owner_approved: false
}
export type ConfirmedMpoChoice = {
  token: string
  selected_frame_index: number
  selected_preview_sha256: string
  preview_data_uri: string
}
const choices = new WeakMap<File, ConfirmedMpoChoice>()

export function confirmedMpoChoice(file: File) {
  return choices.get(file)
}

export async function confirmMpoFixtureFrame(file: File, receipt: PreviewReceipt, index: number) {
  if (!A51D_MPO_FIXTURE ||
      receipt.contract !== 'A51D_MPO_PREVIEW_EXPLICIT_SELECT_FIXTURE_V1' ||
      !receipt.requires_explicit_confirmation ||
      receipt.contract_final_owner_approved !== false) {
    throw Error('베타 MPO 선택용 미승인 테스트 계약입니다.')
  }
  const frame = receipt.frames.find(f => f.index === index)
  if (!frame || !receipt.token) throw Error('선택할 MPO 프레임을 확인해 주세요.')
  // Distinct authenticated POST records the chosen preview action on the
  // server. An attacker can still mimic a click using an authenticated HTTP
  // client: this test-only receipt is NOT a human visual/legal signoff.
  const { request } = await import('../api/client')
  const confirmed = await request<{contract: string; confirmed: boolean;
    frame_index: number; provider_calls: number
  }>('/demo/api/a51d/mpo/confirm', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      token: receipt.token, selected_frame_index: frame.index,
      selected_preview_sha256: frame.preview_png_sha256,
    }),
  })
  if(confirmed.contract !== receipt.contract || confirmed.confirmed !== true ||
     confirmed.frame_index !== frame.index || confirmed.provider_calls !== 0)
    throw Error('서버에서 MPO 선택을 인증하지 못했습니다.')
  const choice: ConfirmedMpoChoice = {
    token: receipt.token,
    selected_frame_index: frame.index,
    selected_preview_sha256: frame.preview_png_sha256,
    preview_data_uri: frame.preview_data_uri,
  }
  choices.set(file, choice)
  return choice
}

export async function requiresMpoFixtureSelection(file: File): Promise<boolean> {
  if (!A51D_MPO_FIXTURE) return false
  // Inspects JPEG APP2 MPF signature independently of ".jpg" / ".mpo" suffix.
  return hasEmbeddedMpoSignature(file)
}

export async function inspectMpoFixture(file: File): Promise<PreviewReceipt> {
  if (!A51D_MPO_FIXTURE) throw Error('MPO 베타 선택은 현재 비활성화되어 있습니다.')
  const form = new FormData()
  form.set('photo', file)
  const { request } = await import('../api/client')
  const receipt = await request<PreviewReceipt>('/demo/api/a51d/mpo/preview', {
    method: 'POST', body: form,
  })
  if (receipt.contract !== 'A51D_MPO_PREVIEW_EXPLICIT_SELECT_FIXTURE_V1' ||
      receipt.frames.length < 2 || !receipt.requires_explicit_confirmation) {
    throw Error('MPO 프레임 정보를 검증할 수 없습니다.')
  }
  return receipt
}
