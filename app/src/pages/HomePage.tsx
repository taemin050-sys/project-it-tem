import { Link } from 'react-router-dom'

export default function HomePage() {
  return (
    <section>
      <h1>제품 사진만 올리면 광고가 완성됩니다</h1>
      <p>제품 정보 입력 → 광고 설정 → 문구 확인 → 이미지 시안 → 내보내기 순서로 진행합니다.</p>
      <Link className="button" to="/product">새 광고 만들기</Link>
      {/* 최근 작업 목록은 11/02 브라우저 자동저장과 함께 추가 */}
    </section>
  )
}
