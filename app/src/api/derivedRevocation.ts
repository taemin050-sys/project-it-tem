import { canRevokeDerivedAdmission, derivedPath, type DerivedRender, type DerivedSnapshot } from './derivedContract.ts'

type Sender = (path: string, options: {method: 'POST'; headers: {'Content-Type': string}; body: string}) => Promise<DerivedRender>

/** Exactly one CAS request. A lost response requires a fresh snapshot, never
 * an automatic retry or a second revocation based on an old admission. */
export function sendDerivedAdmissionRevocation(snapshot: DerivedSnapshot, render: DerivedRender, send: Sender) {
  if (!canRevokeDerivedAdmission(snapshot, render)) throw Error('사용 중지할 보호 시안과 Recipe 수용 권한을 다시 확인해 주세요.')
  return send(`${derivedPath(render.job_id)}/renders/${encodeURIComponent(render.derived_id)}/revoke-admission`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({expected_revision: render.revision, expected_context_sha: snapshot.context_sha,
      expected_admission_sha: render.admission_sha}),
  })
}
