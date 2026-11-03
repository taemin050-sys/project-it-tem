import { getResponse } from 'msw'
import { handlers } from './handlers'

// 개발용 mock: 서비스 워커 없이 페이지 안에서 핸들러를 직접 실행한다.
// 서비스 워커 방식은 브라우저가 유휴 워커를 종료하면 활성 탭 정보를 잃고 요청을
// 실제 서버(localhost:8000)로 그대로 보내 "서버에 연결할 수 없습니다"가 났다.
export async function mockFetch(url: string, init?: RequestInit): Promise<Response> {
  const request = new Request(url, init)
  const response = await getResponse(handlers, request)
  if (!response) throw new Error(`mock 핸들러 없음: ${request.method} ${url}`)
  return response
}
