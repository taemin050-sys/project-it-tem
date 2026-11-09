import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { continueOrStartNew, startNewAdLink } from '../api/useJob'
import Icon from '../components/Icon'
import { SERVICE_NAME } from '../config'
import { useProjectStore } from '../store/projectStore'

const NAV = [
  { href: '#about', label: '서비스 소개' },
  { href: '#how', label: '만드는 방법' },
  { href: '#promise', label: '약속' },
]

const AUDIENCE = [
  {
    icon: 'storefront', tone: 'primary', tag: '스마트스토어 & 쿠팡 셀러',
    title: '화장품 OEM/ODM 1인 셀러 및 스마트스토어 대표님',
    desc: '공장에서 갓 출시된 단품 하나로 마케팅을 시작해야 할 때, 제품 사진 2~5장만 있으면 피드 전용 스튜디오 컷과 소구점 카피가 즉시 완성됩니다.',
  },
  {
    icon: 'payments', tone: 'secondary', tag: '비용 절감형 크리에이티브',
    title: '외주 대행사 비용이 부담스러운 뷰티 소상공인',
    desc: '비싼 촬영 스튜디오 렌탈, 모델 섭외비, 상세페이지 수정 비용을 아끼고 인스타 전환 최적화 소재를 직접 실험할 수 있습니다.',
  },
  {
    icon: 'gavel', tone: 'tertiary', tag: '식약처 규제 점검',
    title: '과대광고·허위표현(식약처 화장품법) 위반이 두려운 초보 마케터',
    desc: "'주름 삭제', '모공 박멸' 등 판매 정지 위험이 있는 금지 문구를 실시간 AI 필터가 걸러내고, 식약처 가이드에 부합하는 안전한 합법적 표현을 제안합니다.",
  },
]

const STEPS = [
  { icon: 'add_photo_alternate', title: '제품 등록', desc: '스마트폰으로 촬영한 누끼 컷 또는 흰 배경 제품 사진과 핵심 성분(병풀, 레티놀 등) 스펙을 간편 등록합니다.' },
  { icon: 'edit_note', title: '기획·카피 검토', desc: '타깃층(2030 수부지 등)에 맞춘 인스타 훅 카피와 식약처 표시광고 규정 적합성 여부를 동시 검토합니다.' },
  { icon: 'magic_button', title: '이미지 검토', desc: '제품 실물 외관을 변형하지 않고, 자연광 무드나 럭셔리 욕실 배경과 자연스럽게 블렌딩된 이미지를 확인합니다.' },
  { icon: 'file_download', title: '최종 결과 다운로드', desc: '인스타그램 피드(4:5), 릴스/스토리(9:16), 텍스트 오버레이 버전까지 바로 게재 가능한 규격 에셋 패키지를 다운로드합니다.' },
]

const PROMISES = [
  {
    icon: 'lock_reset', title: '“제품은 그대로”', sub: 'AI 환각으로 인한 용기·라벨 왜곡 방지',
    desc: '시중 AI 툴처럼 용기 모양이 휘어지거나 영문 브랜드 로고 철자가 뭉개지는 일이 없습니다. 고객이 업로드한 제품 원본 누끼 픽셀을 불변의 마스크 레이어로 완벽 보존합니다.',
  },
  {
    icon: 'format_quote', title: '“카피는 먼저”', sub: '이미지 생성 전 규제 통과된 고효율 후킹 카피 선확정',
    desc: '그림을 먼저 그리고 문구를 억지로 끼워 맞추지 않습니다. 메타(Meta) 인스타그램 알고리즘이 선호하는 카피 구조를 먼저 확정한 후, 문구 분위기와 일치하는 배경 비주얼을 설계합니다.',
  },
  {
    icon: 'policy', title: '“표현은 한 번 더”', sub: '식약처 화장품 표시·광고 가이드라인 정밀 진단',
    desc: '화장품법 제13조 실증 규정과 식약처 최신 행정 처분 사례 데이터를 학습한 특화 엔진이 단어 하나하나를 심사하여, 신고나 과태료 걱정 없는 클린 광고를 보장합니다.',
  },
]

// final-project-docs/result_image의 실제 모델 생성 결과 (864×1080 WebP로 줄여 public/examples에 둠)
const HERO = { src: '/examples/gloss_spring.webp', headline: '봄빛을 머금다', subline: '맑고 산뜻한 나만의 순간' }
const STORY = { src: '/examples/gloss_bubble.webp', title: '글래스팅 컬러 글로스' }
const SHOWCASE = [
  { src: '/examples/gloss_spring.webp', label: '글래스팅 컬러 글로스', quote: '봄빛을 머금다' },
  { src: '/examples/pad_routine.webp', label: '캐롯 카로틴 워터 패드', quote: '가볍게 여는 피부 루틴' },
  { src: '/examples/gloss_pink.webp', label: '글래스팅 컬러 글로스', quote: '말갛게 반짝, 핑크빛!' },
]

function SiteHeader() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  return (
    <header className="site-header">
      <div className="container site-header-inner">
        <div className="site-header-left">
          <Link to="/" className="logo" aria-label={`${SERVICE_NAME} 홈`}>
            <strong>{SERVICE_NAME}</strong>
            <span className="grad-text">AI K-Beauty Studio</span>
          </Link>
          <nav id="site-menu" className={open ? 'site-nav open' : 'site-nav'} aria-label="사이트 메뉴">
            {NAV.map((n) => (
              <a key={n.href} href={n.href} onClick={() => setOpen(false)}>{n.label}</a>
            ))}
            <Link to="/team/evaluations">팀 품질 평가</Link>
          </nav>
        </div>
        <div className="site-header-right">
          <Link className="button small" to="/create" onClick={continueOrStartNew}><Icon name="auto_awesome" className="label-lg" />새 광고 만들기</Link>
          <button type="button" className="menu-toggle" aria-expanded={open} aria-controls="site-menu" onClick={() => setOpen((v) => !v)}>
            {open ? '닫기' : '메뉴'}
          </button>
        </div>
      </div>
    </header>
  )
}

export default function LandingPage() {
  // 결과까지 끝나지 않은 작업: 이어 갈지 새로 시작할지 사용자가 고르게 한다 (말없이 비우지 않음)
  const unfinished = useProjectStore((s) => s.jobId !== null && s.jobId !== s.finishedJobId)
  const productName = useProjectStore((s) => s.product.product_name)

  return (
    <>
      <a className="skip-link" href="#main">본문 바로가기</a>
      <div className="rainbow-bar" aria-hidden="true" />
      <SiteHeader />

      <main id="main" className="landing">
        <div className="glow-blob one" aria-hidden="true" />
        <div className="glow-blob two" aria-hidden="true" />

        <div className="container">
          {unfinished && (
            <div className="resume" role="status">
              <div className="resume-inner">
                <p className="resume-text">
                  <span className="tag tag-primary">임시 저장</span>
                  <span>진행 중인 광고: <b>{productName.trim() ? `[${productName.trim()}]` : '[제품명 미입력]'}</b></span>
                </p>
                <div className="resume-actions">
                  <Link to="/create/product" onClick={startNewAdLink}>새 광고 시작</Link>
                  <Link className="button small" to="/create" onClick={continueOrStartNew}><Icon name="play_arrow" className="label-lg" />이어서 만들기</Link>
                </div>
              </div>
            </div>
          )}

          <section className="hero" aria-labelledby="hero-title">
            <div>
              <span className="tag tag-soft"><Icon name="verified" />K-Beauty 소상공인 식약처 규제 안심 솔루션</span>
              <h1 id="hero-title" className="hero-title">
                <span>사진 몇 장으로 만드는</span>
                <span className="grad-text">광고 한 편.</span>
              </h1>
              <p className="hero-lead">
                화장품 1인 셀러 &amp; 스마트스토어 대표님을 위한 <strong>AI 인스타그램 광고 크리에이터</strong>.
                식약처 화장품 표시광고 규제 사전 점검부터 고감도 피드·스토리 비주얼 완성까지 한 번에 끝냅니다.
              </p>
              <div className="hero-actions">
                <Link className="button lg" to="/create" onClick={continueOrStartNew}>
                  <Icon name="auto_awesome" />광고 시안 만들기<Icon name="arrow_forward" className="icon-forward" />
                </Link>
                <a className="button ghost-white" href="#samples"><Icon name="view_carousel" />샘플 광고 피드 둘러보기</a>
              </div>
            </div>

            <div className="hero-visual" aria-hidden="true">
              <div className="post">
                <div className="post-head">
                  <span className="post-avatar"><span>IT</span></span>
                  <span className="post-name"><b>it_tem_sample<Icon name="verified" /></b><span>Sponsored · {SERVICE_NAME} AI</span></span>
                </div>
                <img className="post-image" src={HERO.src} alt="" />
                <div className="post-icons">
                  <Icon name="favorite" /><Icon name="mode_comment" /><Icon name="send" /><Icon name="bookmark" />
                </div>
                <p className="post-caption"><b>it_tem_sample</b> {HERO.headline} — {HERO.subline}</p>
              </div>
              <div className="story-card">
                <img className="story-thumb" src={STORY.src} alt="" />
                <div>
                  <span className="button-row" style={{ gap: 6 }}>
                    <span className="tag tag-secondary">인스타 스토리 최적화</span>
                    <span className="label-sm text-variant">9:16 비율</span>
                  </span>
                  <b>{STORY.title}</b>
                  <span className="text-variant">후킹 카피 &amp; 컬러 톤앤매너 완벽 동기화</span>
                </div>
                <Icon name="check_circle" />
              </div>
            </div>
          </section>
        </div>

        <section id="about" className="sec tinted" aria-labelledby="about-title">
          <div className="container">
            <div className="sec-head">
              <span className="tag tag-primary tag-upper">Target Audience</span>
              <h2 id="about-title" className="headline-lg">누구를 위한 서비스인가요?</h2>
              <p>전문 대행사 없이도, 혼자서 당당히 광고를 집행할 수 있도록 뷰티 브랜드 대표님의 현실적인 고민을 해결합니다.</p>
            </div>
            <ul className="grid-3">
              {AUDIENCE.map((a) => (
                <li key={a.title} className="feature">
                  <span className={`feature-icon ${a.tone}`}><Icon name={a.icon} /></span>
                  <span className={`label-sm text-${a.tone}`}>{a.tag}</span>
                  <h3 className="headline-sm">{a.title}</h3>
                  <p>{a.desc}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section id="how" className="sec" aria-labelledby="how-title">
          <div className="container">
            <div className="sec-head">
              <span className="tag tag-secondary tag-upper">Easy 4 Steps</span>
              <h2 id="how-title" className="headline-lg">초간단 4단계 인스타 광고 완성 프로세스</h2>
              <p>복잡한 프롬프트 입력이나 디자인 툴 사용 없이, 순서대로 확인만 누르면 전문가급 광고가 탄생합니다.</p>
            </div>
            <ol className="grid-4">
              {STEPS.map((s, i) => (
                <li key={s.title} className="step-tile">
                  <div className="step-tile-top">
                    <span className="step-num" aria-hidden="true">{i + 1}</span>
                    <Icon name={s.icon} />
                  </div>
                  <small>STEP 0{i + 1}</small>
                  <h3 className="headline-sm">{s.title}</h3>
                  <p>{s.desc}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="promise" className="sec tinted" aria-labelledby="promise-title">
          <div className="container">
            <div className="sec-head">
              <span className="tag tag-tertiary tag-upper">Our Core Promise</span>
              <h2 id="promise-title" className="headline-lg">{SERVICE_NAME}이 뷰티 대표님께 드리는 3가지 철칙</h2>
              <p>생성형 AI의 고질적인 환각 오류와 과장 광고 문제를 근본적으로 차단하는 독자적인 파이프라인을 약속드립니다.</p>
            </div>
            <ul className="grid-3">
              {PROMISES.map((p, i) => (
                <li key={p.title} className="promise-card">
                  <div className="promise-inner">
                    <div className="promise-top">
                      <span className="tag tag-primary">PROMISE 0{i + 1}</span>
                      <Icon name={p.icon} />
                    </div>
                    <h3 className="headline-md">{p.title}</h3>
                    <p className="promise-sub">{p.sub}</p>
                    <p>{p.desc}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section id="samples" className="sec" aria-labelledby="samples-title">
          <div className="container">
            <div className="sec-head left">
              <span className="tag tag-primary tag-upper">Live Showcase</span>
              <h2 id="samples-title" className="headline-lg">{SERVICE_NAME}으로 제작된 실제 뷰티 광고 시안</h2>
              <p>다양한 뷰티 카테고리별로 생성된 인스타 광고 에셋입니다.</p>
            </div>
            <ul className="grid-3">
              {SHOWCASE.map((ex) => (
                <li key={ex.src} className="show-card">
                  <div className="show-media">
                    <span className="tag">인스타 피드 (4:5)</span>
                    <img className="show-image" src={ex.src} alt={`${ex.label} 광고 시안: ${ex.quote}`} loading="lazy" />
                    <div className="show-sheet">
                      <small>{ex.label}</small>
                      <p>“{ex.quote}”</p>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="container" aria-labelledby="cta-title">
          <div className="cta-band">
            <h2 id="cta-title">지금 바로 내 화장품으로<br />첫 번째 인스타 광고를 제작해보세요.</h2>
            <p>신용카드 등록 없이 사진만 올리면 끝납니다. 식약처 표시광고 가이드 통과 문구와 감각적인 비주얼을 바로 확인하세요.</p>
            <div className="cta-actions">
              <Link className="button white" to="/create" onClick={continueOrStartNew}><Icon name="auto_awesome" />지금 무료로 광고 만들기</Link>
              <a className="button glass" href="#how">자세한 기능 알아보기<Icon name="chevron_right" /></a>
            </div>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="container site-footer-inner">
          <div className="footer-top">
            <span className="logo"><strong>{SERVICE_NAME}</strong></span>
            <nav className="footer-nav" aria-label="하단 메뉴">
              <a href="#about">서비스 소개</a>
              <a href="#how">만드는 방법</a>
              <Link to="/team/evaluations">공동 검수 센터</Link>
            </nav>
          </div>
          <div className="footer-note">
            <b><Icon name="verified" />화장품 표시·광고 준수 및 책임 고지 가이드라인</b>
            <p>본 서비스({SERVICE_NAME})에서 생성된 인스타그램 피드·스토리 소재와 카피는 화장품법 제13조(부당한 표시·광고 행위 등의 금지) 및 식품의약품안전처 화장품 표시·광고 실증에 관한 규정을 준수하도록 설계된 AI 검토 알고리즘을 거칩니다. 최종 광고 송출 전 의약품 오인 문구, 기능성 심사 번호 및 기능성화장품 기재 누락 여부를 대표자께서 필히 재확인하시기 바랍니다.</p>
          </div>
          <p className="footer-copy">© 2026 {SERVICE_NAME}. 뷰티 소상공인 전용 인스타그램 AI 크리에이티브 파트너.</p>
        </div>
      </footer>
    </>
  )
}
