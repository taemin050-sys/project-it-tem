export const API = "/api/v1";

export type JobStatus =
  | "INPUTS_VALIDATED" | "PLAN_READY" | "COPY_REVIEW_REQUIRED"
  | "COPY_APPROVED" | "COPY_REJECTED" | "IMAGE_REVIEW_REQUIRED"
  | "IMAGE_APPROVED" | "IMAGE_REJECTED" | "COMPLETED";

export type ArtifactKind = "plan" | "copy" | "image" | "final" | "caption";

export interface Job {
  job_id: string;
  status: JobStatus;
  created_at: string;
  assets: Array<{ asset_id: string; original_filename: string; role: string; sha256: string }>;
  plan?: Record<string, unknown>;
  copy_candidate?: { text: string; mock: boolean; compliance_checked: boolean };
  image_candidate?: { mock: boolean; source: string; size: number[] };
  final_output?: { mock: boolean; width: number; height: number; format: string };
  artifacts?: Partial<Record<ArtifactKind, { download_url: string; content_type: string }>>;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: unknown,
  ) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.name = "ApiError";
  }
}

export async function send<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(API + path, init);
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, body?.detail ?? body);
  return body as T;
}

export async function createJob(products: File[], references: File[]): Promise<Job> {
  if (products.length < 2 || products.length > 5 || references.length > 5) {
    throw new Error("제품 사진은 2~5장, 참고 사진은 0~5장이어야 합니다.");
  }
  const form = new FormData();
  products.forEach((f) => form.append("product_images", f));
  references.forEach((f) => form.append("reference_images", f));
  return send<Job>("/jobs", { method: "POST", body: form });
}

export const getJob = (jobId: string) => send<Job>(`/jobs/${encodeURIComponent(jobId)}`);
export const runPlan = (jobId: string, brandName: string, productName: string) =>
  send<Job>(`/jobs/${jobId}/mock/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ brand_name: brandName, product_name: productName }),
  });
export const runCopy = (jobId: string) =>
  send<Job>(`/jobs/${jobId}/mock/copy`, { method: "POST" });
export const approve = (jobId: string, kind: "copy" | "image", approved: boolean) =>
  send<Job>(`/jobs/${jobId}/approvals/${kind}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved }),
  });
export const runImage = (jobId: string) =>
  send<Job>(`/jobs/${jobId}/mock/image`, { method: "POST" });
export const runCompose = (jobId: string) =>
  send<Job>(`/jobs/${jobId}/mock/compose`, { method: "POST" });
