# 이미지 업로드·저장 호환

2026-10-30 · 이미지 모듈 범위

## 입력

LocalAssetStore.put_upload는 디코더가 판별한 PNG, JPEG, WebP, MPO를 받는다.
파일 확장자로 형식을 판정하지 않는다. .jpg 파일 안에 MPO가 들어 있을 수 있다.
MPO는 대표 프레임 0 하나를 선택한다. 보조 프레임을 별도 사진으로 전송하지 않는다.
HEIC/HEIF와 일반 애니메이션은 이번 지원 범위에 포함하지 않는다.
이미 열어 둔 다중 프레임 객체를 put_image로 전달하는 동작은 계속 거절한다.

선택한 정지 사진은 기존 바이트/픽셀 제한, EXIF 회전, ICC→sRGB 변환, RGB/RGBA 정규화와 메타데이터 제거를 거친다.
AssetRef는 최종 PNG의 크기·해시를 나타낸다. 원본 바이트 보존이나 생성 모델의 제품 원형 보존을 의미하지 않는다.

## Windows

Windows에서는 표준 라이브러리의 POSIX 방식 디렉터리 fsync를 호출하지 않는다.
파일 flush/fsync, 파일 닫기, os.replace, SQLite commit 순서는 유지한다.
실제 파일 쓰기·권한·교체·DB 오류는 ASSET_STORAGE_ERROR로 전달한다.
디렉터리 항목의 장애 내구성 보장은 POSIX 경로보다 약하다. 이는 전체 저장 오류를 무시하는 옵션이 아니다.

## 검증

저장소 루트, 이미지 테스트용 가상환경에서 실행한다.

    python -m pytest -c tests/image_generation/pytest.ini tests/image_generation -q

2026-10-30 후보에서 전체 318 tests PASS(3.50s), 자산 관련 36 tests PASS.
Windows 모의 분기는 directory skip, 파일 동기화/닫기/교체 순서, 쓰기·교체·mkdir·DB 실패를 검사한다.
실제 Windows 환경 검증은 NOT_RUN이다. 이 모의 결과로 Windows 실환경 PASS를 주장하지 않는다.

실제 제품 MPO 2개(4032×3024, 2프레임)는 첫 프레임의 EXIF/ICC를 적용한 3024×4032 PNG로 저장·재조회했다.
정규화 기준 픽셀과 일치했고 메타데이터는 제거됐다. 해당 원본은 테스트 저장소에 포함하지 않는다.
별도 Linux Python3.12/Pillow12.3 환경에서도 같은 assets.py 후보로 실제 directory/file fsync와 SQLite 재조회·실패 처리를 확인했다.
최종 1080×1350 광고 합성과 서빙 승인/다운로드 인수는 별도 범위다.
