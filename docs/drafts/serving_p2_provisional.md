# IT-TEM Backend P2 — API 초안 (팀 합의 전)

> 상태: **PROVISIONAL / NOT APPROVED**. 프론트엔드·모델 담당자·PM의 합의 전에는 외부 인터페이스를 확정하거나 운영용으로 사용하지 않습니다.

## 범위

- 화장품 / 인스타그램 피드 최초 업로드 및 작업 레코드 생성
- 제품 사진: 2~5장 필수, 참고 이미지: 0~5장 선택
- PNG/JPEG/WEBP 지원, 손상·빈 파일·중복 이미지·MIME 불일치·과도한 크기 거부
- 파일별 10MiB, 요청 총 60MiB, 최대 4천만 픽셀: 개발용 임시값. 팀 합의 후 설정 조정
- 서버에 개인키/API Key 저장하거나 모델 API 호출하지 않음

## 제안 엔드포인트

| 메서드 | 경로 | 입력 | 출력 |
|---|---|---|---|
| `POST` | `/api/v1/jobs` | `multipart/form-data`: `product_images` 반복 필수, `reference_images` 반복 선택 | `201`: `job_id`, `status`, `created_at`, `assets` |
| `GET` | `/api/v1/jobs/{job_id}` | 경로에 작업 ID | `200`: 작업 JSON |
| `GET` | `/api/v1/jobs/{job_id}/assets/{asset_id}` | 경로에 작업 ID / 이미지 ID | 이미지 바이너리 다운로드 |

예시 응답(실제 ID·해시는 요청마다 달라짐):

```json
{
  "job_id": "f7a3d06896e44a92a8c0c8ed4b7f5c32",
  "status": "INPUTS_VALIDATED",
  "created_at": "2026-10-23T00:00:00+00:00",
  "assets": [
    {
      "asset_id": "11111111111111111111111111111111",
      "role": "product",
      "original_filename": "product-1.png",
      "content_type": "image/png",
      "size_bytes": 34291,
      "width": 1024,
      "height": 1024,
      "sha256": "<sha256 of file>"
    }
  ]
}
```

## 오류

- `422`: 입력 개수·유형·이미지 인코딩·중복·MIME 불일치 오류 (또는 필드 누락)
- `413`: 임시 업로드 크기 제한 초과
- `404`: 존재하지 않는 작업 또는 이미지 ID
- 성공한 초기 상태: `INPUTS_VALIDATED`. 후속 기획/카피/이미지/승인 상태는 팀 합의 전이므로 추가하지 않음

## 스토리지 / 운영 제약

- `.runtime/jobs/<32자리 UUID-hex>/` 디렉터리에 이미지와 `job.json`을 저장함 (`.gitignore` 제외)
- 원본 파일명은 메타데이터에만 보존하고 저장 파일명은 난수 ID로 지정함
- 신규 작업의 이미지 저장 및 `job.json` 생성 실패 시 생성 중인 디렉터리 정리; JSON 최종 반영 시 원자적 교체 수행
- 단일 Uvicorn worker 전용. 여러 worker/여러 인스턴스·수평확장은 DB와 object storage 기반 원자적 작업 계약으로 전환 필요
- 현재 인증·인가, 요청 rate limit, 과금, 외부 접근 제어 미구현. `127.0.0.1` 바인딩으로 내부 검증에만 사용
- 상태 전이·승인·모델 실행·최종 4:5 PNG 합성은 **본 패치에 포함되지 않음**

## 확인 및 합의해야 할 사항

1. 이미지 개수·용량·형식의 공식 계약 및 오류 응답 형식
2. 프론트엔드에서 사용할 필드명/상태값 및 stage별 승인 API
3. 프로젝트/세션 인증 및 파일 다운로드 권한
4. 데이터 보존·삭제 정책, 재시도/멱등성 키
5. 향후 VM 외부 배포 시 DB 및 object storage 선택

합의 후 `docs/interface_spec.md`에 확정 내용 반영. 이 초안은 확정 문서를 대체하지 않습니다.
