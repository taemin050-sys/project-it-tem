import type { LiveState } from '../api/liveMapping'

// Read-only navigation: never calls Provider or queues a Job.
export function resumePath(state:LiveState):'/create/copy'|'/create/draft'|'/create/export' {
  if(state==='COMPLETED')return '/create/export'
  if(state==='INPUT_STORED' || state==='COPY_REVIEW_REQUIRED' || state==='COPY_REJECTED')
    return '/create/copy'
  return '/create/draft'
}

export function resumeLabel(state:LiveState):string {
  const labels:Record<LiveState,string>={
    INPUT_STORED:'AI 기획·카피 생성 중',
    COPY_REVIEW_REQUIRED:'카피 검토',
    COPY_APPROVED:'이미지 준비',
    COPY_REJECTED:'카피 수정',
    PROMPT_READY:'이미지 생성 준비',
    IMAGE_REVIEW_REQUIRED:'이미지 검토',
    IMAGE_APPROVED:'최종 이미지 준비',
    IMAGE_REJECTED:'이미지 재생성 검토',
    COMPLETED:'완료',
  }
  return labels[state]
}
