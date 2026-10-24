/** PROVISIONAL — read docs/drafts/p4a_react_fastapi_contract_provisional.md. */
export type JobStatus =
  | "INPUTS_VALIDATED" | "PLAN_READY" | "COPY_REVIEW_REQUIRED"
  | "COPY_APPROVED" | "IMAGE_REVIEW_REQUIRED" | "IMAGE_APPROVED"
  | "COMPLETED" | "COPY_REJECTED" | "IMAGE_REJECTED";

export type ArtifactKind = "plan" | "copy" | "image" | "final" | "caption";
export interface JobAsset {
  asset_id: string; role: "product" | "reference";
  original_filename: string; content_type: string; width: number; height: number;
  sha256: string; size_bytes: number;
}
export interface Job {
  job_id: string; status: JobStatus; created_at: string;
  assets: JobAsset[];
  artifacts?: Partial<Record<ArtifactKind, {
    kind: ArtifactKind; content_type: string; size_bytes: number; download_url: string;
  }>>;
  plan?: Record<string, unknown>;
  copy_candidate?: { text: string; mock: boolean; compliance_checked: boolean };
  image_candidate?: { mock: boolean; source: string; size: number[] };
  final_output?: { mock: boolean; width: number; height: number; format: string };
}

const API = "/api/v1"; // Use a same-origin dev proxy; do not expose VM 8000 publicly.
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API}${path}`, init);
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body?.detail;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail ?? body));
  }
  return body as T;
}
export async function createJob(products: File[], references: File[] = []): Promise<Job> {
  if (products.length < 2 || products.length > 5 || references.length > 5) {
    throw new Error("제품 사진 2~5장, 참고 사진 0~5장을 선택하세요");
  }
  const form = new FormData();
  products.forEach(file => form.append("product_images", file));
  references.forEach(file => form.append("reference_images", file));
  return request<Job>("/jobs", { method: "POST", body: form });
}
export const getJob = (id: string) => request<Job>(`/jobs/${encodeURIComponent(id)}`);
export const capabilities = () => request<{text_provider_ready: boolean, image_provider_ready: boolean}>("/capabilities");
export function runPlan(id: string, input: {brand_name:string; product_name:string; product_facts?:string[]}, mode: "mock"|"ai") {
  const body = mode === "ai" ? input : {brand_name: input.brand_name, product_name: input.product_name};
  return request<Job>(`/jobs/${encodeURIComponent(id)}/${mode}/plan`, {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
  });
}
export const runCopy = (id: string, mode: "mock"|"ai") => request<Job>(`/jobs/${encodeURIComponent(id)}/${mode}/copy`, {method:"POST"});
export function approve(id: string, kind:"copy"|"image", approved:boolean) {
  return request<Job>(`/jobs/${encodeURIComponent(id)}/approvals/${kind}`, {
    method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({approved}),
  });
}
export const runMockImage = (id:string) => request<Job>(`/jobs/${encodeURIComponent(id)}/mock/image`, {method:"POST"});
export const runMockComposition = (id:string) => request<Job>(`/jobs/${encodeURIComponent(id)}/mock/compose`, {method:"POST"});
export const artifactUrl = (job:Job, kind:ArtifactKind) => job.artifacts?.[kind]?.download_url ?? null;
