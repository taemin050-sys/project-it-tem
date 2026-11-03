import { useEffect, useState } from 'react'

// 파일·blob 미리보기 URL. effect 안에서 만들고 정리해야 StrictMode 재마운트 뒤에도 해제된 URL을 쓰지 않는다
// (useMemo로 만들고 cleanup에서 해제하면 재마운트 때 같은 URL이 이미 해제돼 이미지·PNG 저장이 깨진다)
export function useObjectUrls(blobs: readonly Blob[]): string[] {
  const [urls, setUrls] = useState<string[]>([])
  useEffect(() => {
    const next = blobs.map((b) => URL.createObjectURL(b))
    // 브라우저 URL 등록·해제(외부 자원)와 맞추는 effect라 여기서 state를 갱신한다
    // oxlint-disable-next-line react/set-state-in-effect
    setUrls(next)
    return () => next.forEach((u) => URL.revokeObjectURL(u))
  }, [blobs])
  return urls
}
