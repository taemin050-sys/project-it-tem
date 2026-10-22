import { API_BASE_URL, REQUEST_TIMEOUT_MS } from '../config'

export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// 오류 코드 정의는 이형기·pi 소유. 확정 전까지 HTTP 상태 기준 기본 문구만 둔다
const STATUS_MESSAGES: Record<number, string> = {
  413: '파일 용량이 너무 큽니다. 더 작은 사진으로 다시 시도해 주세요.',
  422: '입력 내용을 확인해 주세요. 사진 형식이나 필수 항목에 문제가 있습니다.',
  429: '지금 요청이 많습니다. 잠시 후 다시 시도해 주세요.',
  503: '서버가 일시적으로 바쁩니다. 잠시 후 다시 시도해 주세요.',
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'TimeoutError') {
      throw new ApiError(0, '서버 응답이 늦어지고 있습니다. 잠시 후 다시 시도해 주세요.')
    }
    throw new ApiError(0, '서버에 연결할 수 없습니다. 네트워크 상태를 확인해 주세요.')
  }
  if (!res.ok) {
    throw new ApiError(res.status, STATUS_MESSAGES[res.status] ?? `요청에 실패했습니다. (오류 ${res.status})`)
  }
  return res.json() as Promise<T>
}
