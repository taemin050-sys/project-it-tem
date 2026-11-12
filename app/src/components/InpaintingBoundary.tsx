import { Component, type ReactNode } from 'react'

export default class InpaintingBoundary extends Component<{children:ReactNode},{failed:boolean}> {
  state={failed:false}
  static getDerivedStateFromError(){return {failed:true}}
  render(){
    return this.state.failed?<section role="alert" data-testid="inpaint-load-error">
      <p>부분 수정 도구를 불러오지 못했습니다. 기존 광고와 다운로드는 유지됩니다.</p>
      <button type="button" className="button secondary" onClick={()=>window.location.reload()}>부분 수정 도구 다시 불러오기</button>
    </section>:this.props.children
  }
}
