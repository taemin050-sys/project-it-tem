/**
 * IT-TEM legacy feature HTTP 예제. 현 dev(P1)에는 POST /api/v1/jobs가 아직 없음.
 * 실제 접근 URL은 팀 승인 후 Vite proxy 또는 server origin. localhost는 사용자의 컴퓨터.
 * ProductInput v0.5 필드(목적/기능성 등)는 현재 legacy /jobs API에 없으므로 임의 추가 금지.
 */
export async function createLegacyJob(baseUrl: string, productFiles: File[], referenceFiles: File[] = []) {
  const form = new FormData();
  productFiles.forEach((file) => form.append("product_images", file));
  referenceFiles.forEach((file) => form.append("reference_images", file));
  const response = await fetch(baseUrl.replace(/\/$/, "") + "/api/v1/jobs", {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    throw new Error("Upload failed: HTTP " + response.status);
  }
  return await response.json(); // direct Job JSON, not a common {data: ...} wrapper
}

/**
 * 이 예제는 current deployed API를 단정하지 않는다. v0.2 ProductInput은
 * docs/contracts/fixtures/product_input.json 참고. 신규 wire endpoint 확정 후 재작성.
 */
