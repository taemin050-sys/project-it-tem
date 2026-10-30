import { API_BASE_URL, REQUEST_TIMEOUT_MS, USE_MOCK } from '../config'

export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// 오류 코드 정의는 이형기·pi 소유. 확정 전까지 HTTP 상태 기준 기본 문구만 둔다
const STATUS_MESSAGES: Record<number, string> = {
  404: '작업을 찾을 수 없습니다. 서버가 다시 시작됐거나 만료된 작업일 수 있으니 제품 정보에서 다시 시작해 주세요.',
  409: '이미 처리됐거나 지금 진행할 수 없는 단계입니다. 현재 상태를 다시 불러왔습니다.',
  413: '파일 용량이 너무 큽니다. 더 작은 사진으로 다시 시도해 주세요.',
  422: '입력 내용을 확인해 주세요. 사진 형식·개수, 같은 사진을 두 번 올렸는지, 필수 항목을 확인해 주세요.',
  429: '지금 요청이 많습니다. 잠시 후 다시 시도해 주세요.',
  503: '서버가 일시적으로 바쁩니다. 잠시 후 다시 시도해 주세요.',
}

type Options = RequestInit & { timeoutMs?: number }

export async function send(path: string, { timeoutMs = REQUEST_TIMEOUT_MS, ...init }: Options = {}): Promise<Response> {
  let res: Response
  try {
    const url = `${API_BASE_URL}${path}`
    const options = { ...init, signal: AbortSignal.timeout(timeoutMs) }
    res = USE_MOCK
      ? await (await import('../mocks/mockFetch')).mockFetch(url, options)
      : await fetch(url, options)
  } catch (e) {
    if (e instanceof DOMException && e.name === 'TimeoutError') {
      // 응답을 못 받았을 뿐 서버는 처리했을 수 있다 — 다시 보내기 전에 상태부터 확인하게 한다
      throw new ApiError(0, '서버 응답을 받지 못했습니다. 서버에서는 처리 중이거나 이미 끝났을 수 있으니, 잠시 후 상태를 다시 확인해 주세요.')
    }
    throw new ApiError(0, '서버에 연결할 수 없습니다. 네트워크 상태를 확인해 주세요.')
  }
  if (!res.ok) {
    throw new ApiError(res.status, STATUS_MESSAGES[res.status] ?? `요청에 실패했습니다. (오류 ${res.status})`)
  }
  return res
}

export async function request<T>(path: string, options?: Options): Promise<T> {
  return (await send(path, options)).json() as Promise<T>
}
