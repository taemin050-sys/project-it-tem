import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { continueOrStartNew } from '../api/useJob'
import FluidAdPreview from '../components/FluidAdPreview'
import { SERVICE_NAME } from '../config'
import { adExamples, mockCopyReview } from '../mocks/sampleResult'
import AdCanvas from '../renderer/AdCanvas'

const NAV = [
  { href: '#about', label: '서비스 소개' },
  { href: '#how', label: '만드는 방법' },
  { href: '#promise', label: '약속' },
]

const AUDIENCE = [
  '디자이너를 따로 두기 어려운 소상공인',
  '온라인 쇼핑몰을 운영하는 판매자',
  '화장품·뷰티 제품을 판매하는 브랜드',
  'SNS 광고 소재가 필요하지만 제작이 번거로운 분',
]

const STEPS = [
  { no: '01', tag: 'Upload', title: '제품 등록', desc: '같은 제품 사진 2~5장과 제품명·특징·광고 목적을 입력합니다. 배경 참고 사진은 선택입니다.' },
  { no: '02', tag: 'Copy', title: '기획·카피 검토', desc: 'AI 사전 조사 요약과 카피, 표현 검수 결과를 확인하고 카피를 승인합니다.' },
  { no: '03', tag: 'Image', title: '이미지 검토', desc: '승인한 카피로 만든 이미지가 원본 제품과 같은지 확인합니다.' },
  { no: '04', tag: 'Export', title: '최종 결과', desc: '1080×1350 광고 이미지와 게시글 본문·해시태그를 저장합니다.' },
]

const PROMISES = [
  {
    no: '01',
    title: '제품은 그대로.',
    desc: '올려 주신 제품 사진을 바탕으로 이미지를 만듭니다. 제품의 모양·색·라벨이 원본과 같은지 직접 확인하고 승인해야 다음으로 넘어갑니다.',
    where: '확인하는 곳 · 03 이미지 검토',
  },
  {
    no: '02',
    title: '카피는 먼저.',
    desc: '이미지를 만들기 전에 카피를 먼저 확인하고 승인합니다. AI가 조사한 내용은 사용자 입력·검색 결과·AI 추론으로 나눠 보여 드립니다.',
    where: '확인하는 곳 · 02 기획·카피 검토',
  },
  {
    no: '03',
    title: '표현은 한 번 더.',
    desc: '화장품 광고에서 주의가 필요한 표현을 표시하고 대체 문구를 제안합니다. 위반 의심 표현이 있으면 승인할 수 없습니다. 참고용 안내이며 게시 전 최종 확인 책임은 사용자에게 있습니다.',
    where: '확인하는 곳 · 02 기획·카피 검토',
  },
]

const demo = mockCopyReview('blocked')
const demoImage = adExamples[1].imageUrl

// 실제 화면 요소를 축소해 보여주는 장식 (스크린리더에서는 숨김)
const STEP_DEMOS = [
  <div className="demo-slots" key="upload">
    <span className="demo-slot"><img src={demoImage} alt="" /></span>
    <span className="demo-slot"><img src={demoImage} alt="" /></span>
    <span className="demo-slot">+</span>
    <span className="demo-meta">2 / 5</span>
  </div>,
  <div className="demo-copy" key="copy">
    <strong>{demo.copy.ad_copy.headline}</strong>
    <span><mark>{demo.report.issues[0].text}</mark> → {demo.report.issues[0].suggestion}</span>
  </div>,
  <div className="demo-export" key="image">
    <AdCanvas imageUrl={demoImage} previewScale={0.06} />
    <span>원본 제품과 비교</span>
  </div>,
  <div className="demo-export" key="export">
    <AdCanvas imageUrl={demoImage} copy={demo.copy.ad_copy} previewScale={0.06} />
    <span>PNG · 1080×1350</span>
  </div>,
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
        <Link to="/" className="logo" aria-label={`${SERVICE_NAME} 홈`}>{SERVICE_NAME}</Link>
        <nav id="site-menu" className={open ? 'site-nav open' : 'site-nav'} aria-label="사이트 메뉴">
          {NAV.map((n) => (
            <a key={n.href} href={n.href} onClick={() => setOpen(false)}>{n.label}</a>
          ))}
        </nav>
        <Link className="button small header-cta" to="/create" onClick={continueOrStartNew}>광고 만들기</Link>
        <button
          type="button"
          className="menu-toggle"
          aria-expanded={open}
          aria-controls="site-menu"
          onClick={() => setOpen((v) => !v)}
        >
          {open ? '닫기' : '메뉴'}
        </button>
      </div>
    </header>
  )
}

export default function LandingPage() {
  const hero = adExamples[0]

  return (
    <>
      <a className="skip-link" href="#main">본문 바로가기</a>
      <SiteHeader />

      <main id="main">
        <section className="container hero" aria-labelledby="hero-title">
          <div className="hero-copy">
            <p className="hero-label">소상공인을 위한 제품 광고 제작 도구</p>
            <h1 id="hero-title" className="hero-title">
              <span>사진 몇 장.</span>
              <span>광고 한 편.</span>
            </h1>
            <p className="hero-lead">제품 사진만 준비하세요. 복잡한 디자인 작업 없이 광고 시안을 만들어보세요.</p>
            <div className="hero-actions">
              <Link className="button" to="/create" onClick={continueOrStartNew}>광고 시안 만들기</Link>
              <a className="text-link" href="#how">만드는 방법 보기</a>
            </div>
            <p className="hero-note">제품 사진 업로드부터 PNG 저장까지</p>
          </div>
          <figure className="hero-visual ad-figure">
            <FluidAdPreview imageUrl={hero.imageUrl} copy={hero.copy} />
            <figcaption><span>{hero.mood}</span><span>예시 시안</span></figcaption>
          </figure>
        </section>

        <section className="section surface" aria-labelledby="examples-title">
          <div className="container">
            <div className="section-head">
              <div>
                <p className="eyebrow">Examples</p>
                <h2 id="examples-title" className="section-title">같은 제품, 다른 분위기</h2>
              </div>
              <p className="section-desc">
                AI가 정한 콘셉트와 배경 참고 사진에 따라 시안의 인상이 달라집니다.
                아래 이미지는 서비스 이해를 돕기 위한 예시 시안이며, 실제 생성 결과와 다를 수 있습니다.
              </p>
            </div>
            <ul className="gallery">
              {adExamples.map((ex) => (
                <li key={ex.mood}>
                  <figure className="ad-figure">
                    <FluidAdPreview imageUrl={ex.imageUrl} copy={ex.copy} />
                    <figcaption><span>{ex.mood}</span><span>예시 시안</span></figcaption>
                  </figure>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section id="about" className="section container about" aria-labelledby="about-title">
          <div>
            <p className="eyebrow">About</p>
            <h2 id="about-title" className="section-title">디자인이 막막한 사장님을 위한 광고 도구</h2>
          </div>
          <div className="about-body">
            <p className="about-lead">
              {SERVICE_NAME}은 이미지를 마음대로 그려 내는 생성기가 아니라, 내 제품 사진으로 광고 시안을 만드는 실용적인 도구입니다.
              프롬프트를 쓰지 않고 제품 정보와 선택지만으로 진행합니다.
            </p>
            <h3 className="list-title">이런 분께 맞습니다</h3>
            <ul className="audience">
              {AUDIENCE.map((a) => <li key={a}>{a}</li>)}
            </ul>
          </div>
        </section>

        <section id="how" className="section how" aria-labelledby="how-title">
          <div className="container">
            <div className="section-head">
              <div>
                <p className="eyebrow">How it works</p>
                <h2 id="how-title" className="section-title">네 단계면 충분합니다</h2>
              </div>
              <p className="section-desc">각 단계는 실제 광고 만들기 화면과 같은 순서로 진행됩니다.</p>
            </div>
            <ol className="steps-grid">
              {STEPS.map((s, i) => (
                <li key={s.no} className="step-card">
                  <div className="step-card-head">
                    <span className="step-no">{s.no}</span>
                    <span className="eyebrow">{s.tag}</span>
                  </div>
                  <h3>{s.title}</h3>
                  <p>{s.desc}</p>
                  <div className="step-demo" aria-hidden="true">{STEP_DEMOS[i]}</div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="promise" className="section promise" aria-labelledby="promise-title">
          <div className="container">
            <div className="section-head">
              <div>
                <p className="eyebrow">Our promise</p>
                <h2 id="promise-title" className="section-title">세 가지를 지킵니다</h2>
              </div>
            </div>
            <ul className="promise-list">
              {PROMISES.map((p) => (
                <li key={p.no} className="promise-item">
                  <span className="promise-no">{p.no}</span>
                  <h3>{p.title}</h3>
                  <p>{p.desc}</p>
                  <p className="promise-where">{p.where}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="section container" aria-labelledby="cta-title">
          <div className="cta-panel">
            <div>
              <h2 id="cta-title">시작은 제품 사진.</h2>
              <p>내 제품으로 광고 시안을 만들어보세요.</p>
            </div>
            <Link className="button dark" to="/create" onClick={continueOrStartNew}>광고 시안 만들기</Link>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="container site-footer-inner">
          <span className="logo logo-sm">{SERVICE_NAME}</span>
          <span>생성형 AI 기반 소상공인 광고 콘텐츠 제작 서비스</span>
          <span>© 2026 {SERVICE_NAME}</span>
        </div>
      </footer>
    </>
  )
}
