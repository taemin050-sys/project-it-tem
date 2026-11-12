# IT-TEM 고도화 Lab 작업 범위

- 사용자 요청에 따른 독립 워크트리이며 `lab/ittem-enhancement-20261112`에서 작업한다. 기준 소스는 `f2066033f7253859b638be04ffa8674d90114457`이다.
- 격리 목적에 따라 PR 대상은 `lab/ittem-enhancement-baseline-20261112`이다. 기존 CONTRIBUTING의 일반 `dev` 통합 절차는 실제 승격 시 적용하며 Lab 정리를 위해 `dev`를 병합·rebase하지 않는다.
- 원본 B·Track A·공식 dev/main·운영 소스·systemd·DB·Job·Queue·Artifact를 Lab 작업 때문에 변경하지 않는다. 배포·공통 통합은 명시적으로 요청된 범위에서 별도로 수행한다.
- `.venv`·`app/node_modules`·환경변수·캐시·임시 런타임은 별도 구성한다. 다른 워크트리의 쓰기 가능한 의존성이나 운영 데이터를 링크하지 않는다.
- 키·원본 제품 사진·실제 사용자 산출물·DB·Provider Receipt 원문을 공개 Git에 추가하지 않는다. 소스·라이선스·공개 가능한 검증 요약·해시를 관리한다.
- CODE·FIXTURE·REAL·HUMAN·독립 C 감사·RELEASE를 구분한다. `NOT_RELEASE_READY`를 유지하고 동일 소스의 기존 검증은 적절히 재사용한다.
- 사용자 책임 확인은 검수 경고를 없애거나 법적 적합성을 보증하지 않는다. 현재 카피의 동의 기록·F09 무결성·Actor ACL·UNKNOWN 및 자동 유료 재시도 금지 계약을 유지한다.
