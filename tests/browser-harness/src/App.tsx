import { useCallback, useEffect, useState } from "react";
import {
  ApiError, approve, createJob, getJob, runCompose, runCopy, runImage, runPlan,
  type ArtifactKind, type Job,
} from "./api";

const stepNames: Record<string, string> = {
  INPUTS_VALIDATED: "사진 입력 검증 완료",
  PLAN_READY: "기획 초안 생성",
  COPY_REVIEW_REQUIRED: "카피 검토 대기",
  COPY_APPROVED: "카피 승인 완료",
  COPY_REJECTED: "카피 거절 (종료)",
  IMAGE_REVIEW_REQUIRED: "이미지 검토 대기",
  IMAGE_APPROVED: "이미지 승인 완료",
  IMAGE_REJECTED: "이미지 거절 (종료)",
  COMPLETED: "합성·다운로드 준비 완료",
};

export default function App() {
  const [job, setJob] = useState<Job | null>(null);
  const [products, setProducts] = useState<File[]>([]);
  const [references, setReferences] = useState<File[]>([]);
  const [brand, setBrand] = useState("라움");
  const [productName, setProductName] = useState("데일리 크림");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [info, setInfo] = useState("아직 시작하지 않았습니다.");

  const refresh = useCallback(async (id: string) => {
    const current = await getJob(id);
    setJob(current);
    setInfo(`서버 Job 재조회 완료: ${current.status}`);
    return current;
  }, []);

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("job");
    if (id && /^[a-f0-9]{32}$/.test(id)) {
      void refresh(id).catch((error: unknown) =>
        setErr(error instanceof Error ? error.message : String(error))
      );
    }
  }, [refresh]);

  async function run(label: string, fn: () => Promise<Job>) {
    if (busy) return;
    setBusy(true);
    setErr("");
    try {
      const updated = await fn();
      setJob(updated);
      setInfo(`${label} 완료: ${updated.status}`);
      if (updated.job_id) {
        window.history.replaceState(null, "", `?job=${encodeURIComponent(updated.job_id)}`);
      }
    } catch (error) {
      const prefix = error instanceof ApiError ? `HTTP ${error.status}` : "클라이언트 오류";
      setErr(`${prefix}: ${error instanceof Error ? error.message : String(error)}`);
      if (error instanceof ApiError && error.status === 409 && job?.job_id) {
        try {
          const latest = await getJob(job.job_id);
          setJob(latest);
          setInfo("409 충돌: Job 상태를 서버에서 다시 조회했습니다.");
        } catch {
          setInfo("409 충돌 후 Job 재조회 실패. 다시 조회를 선택하세요.");
        }
      }
    } finally {
      setBusy(false);
    }
  }

  async function onUpload() {
    await run("업로드", () => createJob(products, references));
  }

  // Download through the real server URL, surface an HTTP error in the UI,
  // and save a native Blob file. No JSON/base64 or model call involved.
  async function download(kind: "final" | "caption") {
    const url = job?.artifacts?.[kind]?.download_url;
    if (!url) return;
    setErr("");
    try {
      const response = await fetch(url);
      if (!response.ok) throw new ApiError(response.status, `Artifact ${kind} is unavailable`);
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = kind === "final" ? "final_mock.png" : "caption.txt";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      setInfo(`${kind} 파일 다운로드 요청 완료`);
    } catch (error) {
      const description = error instanceof Error ? error.message : String(error);
      setErr(`다운로드 실패${error instanceof ApiError ? " (HTTP " + error.status + ")" : ""}: ${description}`);
      setInfo("다운로드 오류: Job 상태를 확인하고 다시 시도해 주세요.");
    }
  }

  const status = job?.status ?? "";
  const artifactUrl = (kind: ArtifactKind) => job?.artifacts?.[kind]?.download_url;

  function action(testid: string, title: string, valid: string, fn: () => Promise<Job>) {
    return (
      <button type="button" data-testid={testid} disabled={!job || busy || status !== valid}
        onClick={() => void run(title, fn)}>{title}</button>
    );
  }

  return (
    <main>
      <header>
        <div className="eyebrow">IT-TEM · API integration smoke harness</div>
        <h1>광고 생성 B0 브라우저 검증</h1>
        <p>권혁상 님의 정식 React 제품 화면이 아닌 <strong>별도 통합 시험용 화면</strong>입니다.</p>
        <div className="labels"><span data-testid="mode">MOCK ONLY</span><span>Live · Compliance 검수 없음</span><span>서버: localhost Vite Proxy</span></div>
      </header>
      <section>
        <h2>1 · 제품 이미지와 입력</h2>
        <p>제품 사진은 같은 상품의 서로 다른 사진 2~5장을 순서대로 선택하세요. 첫 번째 사진은 정면을 권장합니다.</p>
        <div className="fields">
          <label>제품 사진 <input id="product-files" data-testid="products" type="file" multiple accept="image/png,image/jpeg,image/webp"
            onChange={(e) => setProducts(Array.from(e.currentTarget.files ?? []))}/></label>
          <label>참고 사진 (선택) <input id="ref-files" data-testid="references" type="file" multiple accept="image/png,image/jpeg,image/webp"
            onChange={(e) => setReferences(Array.from(e.currentTarget.files ?? []))}/></label>
          <label>브랜드명 <input data-testid="brand" value={brand} onChange={(e) => setBrand(e.target.value)}/></label>
          <label>제품명 <input data-testid="product-name" value={productName} onChange={(e) => setProductName(e.target.value)}/></label>
        </div>
        <p className="fine">선택된 제품 사진 {products.length}장 · 참고 사진 {references.length}장</p>
        <button type="button" data-testid="upload" disabled={busy || products.length < 2 || products.length > 5 || references.length > 5}
          onClick={() => void onUpload()}>업로드 · Job 생성</button>
      </section>
      <section>
        <h2>2 · Job 상태와 단계별 실행</h2>
        <p className="id" data-testid="job-id">{job?.job_id ?? "Job 미생성"}</p>
        <p>현재 상태: <strong data-testid="status">{status || "NOT_STARTED"}</strong> — {stepNames[status] ?? "업로드 대기"}</p>
        <div className="actions">
          {action("plan", "Mock 기획", "INPUTS_VALIDATED", () => runPlan(job!.job_id, brand, productName))}
          {action("copy", "Mock 카피", "PLAN_READY", () => runCopy(job!.job_id))}
          {action("copy-approve", "카피 승인", "COPY_REVIEW_REQUIRED", () => approve(job!.job_id, "copy", true))}
          {action("copy-reject", "카피 거절", "COPY_REVIEW_REQUIRED", () => approve(job!.job_id, "copy", false))}
          {action("image", "Mock 이미지", "COPY_APPROVED", () => runImage(job!.job_id))}
          {action("image-approve", "이미지 승인", "IMAGE_REVIEW_REQUIRED", () => approve(job!.job_id, "image", true))}
          {action("image-reject", "이미지 거절", "IMAGE_REVIEW_REQUIRED", () => approve(job!.job_id, "image", false))}
          {action("compose", "Mock 합성", "IMAGE_APPROVED", () => runCompose(job!.job_id))}
        </div>
        <button type="button" data-testid="refresh" disabled={!job || busy}
          onClick={() => void run("재조회", () => refresh(job!.job_id))}>서버에서 현재 Job 조회</button>
        {err && <p className="error" data-testid="error" role="alert">{err}</p>}
        <p className="fine" data-testid="info">{info}</p>
      </section>
      <section>
        <h2>3 · 카피 / 이미지 / 다운로드</h2>
        <div className="two">
          <div>
            <h3>카피 초안</h3>
            <p data-testid="copy-text">{job?.copy_candidate?.text ?? "카피 미생성"}</p>
            <p className="warning" data-testid="compliance">Compliance 검증: {job?.copy_candidate?.compliance_checked === false ? "NOT CHECKED (Mock)" : "실제 검수 없음"}</p>
          </div>
          <div>
            <h3>이미지 산출물</h3>
            <p data-testid="final-spec">{job?.final_output ? `${job.final_output.width}×${job.final_output.height} ${job.final_output.format}` : "합성 전"}</p>
            {artifactUrl("image") && <a data-testid="image-download" href={artifactUrl("image")}>Mock 이미지 열기</a>}
          </div>
        </div>
        <div className="downloads">
          {artifactUrl("final") && <button type="button" data-testid="final-download" onClick={() => void download("final")}>최종 PNG 다운로드</button>}
          {artifactUrl("caption") && <button type="button" data-testid="caption-download" onClick={() => void download("caption")}>UTF-8 캡션 다운로드</button>}
        </div>
      </section>
      <footer>현재 API: P2/P3 B0 Mock 10개 · + Health 1개. 신규 7개 HTTP Wire 미동결. 비밀키·유료 모델 호출 없음.</footer>
    </main>
  );
}
