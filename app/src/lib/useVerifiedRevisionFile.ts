import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { getBlob } from '../api/jobs'
import { useObjectUrls } from './useObjectUrls'

export function useFile(path: string | undefined, sha: string | null | undefined) {
  const query = useQuery({queryKey: ['revision-artifact', path], enabled: Boolean(path && sha),
    retry: false, staleTime: Infinity, refetchOnWindowFocus: false, queryFn: async () => {
      const blob = await getBlob(path!)
      const digest = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer())
      const actual = Array.from(new Uint8Array(digest), n => n.toString(16).padStart(2, '0')).join('')
      if (actual !== sha) throw Error('수정본 파일의 SHA-256이 일치하지 않습니다.')
      return blob
    }})
  const blobs = useMemo(() => query.data ? [query.data] : [], [query.data])
  const [url] = useObjectUrls(blobs)
  return {url, query}
}

