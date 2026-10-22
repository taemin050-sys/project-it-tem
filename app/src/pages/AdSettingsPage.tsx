import { useMutation } from '@tanstack/react-query'
import { Navigate, useNavigate } from 'react-router-dom'
import { createJob } from '../api/jobs'
import { AD_PRESETS } from '../config'
import { useProjectStore } from '../store/projectStore'
import type { AdSettings } from '../types/draft'

const LABELS: Record<keyof AdSettings, string> = {
  purpose: '광고 목적',
  channel: '채널',
  tone: '문구 톤',
  mood: '분위기',
}

export default function AdSettingsPage() {
  const navigate = useNavigate()
  const { images, product, settings, setSettings, setJobId } = useProjectStore()
  const mutation = useMutation({
    mutationFn: () => createJob(images, product, settings),
    onSuccess: ({ job_id }) => {
      setJobId(job_id)
      navigate('/copy')
    },
  })

  if (images.length === 0) return <Navigate to="/product" replace />

  return (
    <section className="form">
      <h1>광고 설정</h1>
      {(Object.keys(AD_PRESETS) as (keyof AdSettings)[]).map((key) => (
        <fieldset key={key}>
          <legend>{LABELS[key]}</legend>
          <div className="chips">
            {AD_PRESETS[key].map((v) => (
              <button
                key={v}
                type="button"
                className={settings[key] === v ? 'chip selected' : 'chip'}
                aria-pressed={settings[key] === v}
                onClick={() => setSettings({ [key]: v })}
              >
                {v}
              </button>
            ))}
          </div>
        </fieldset>
      ))}

      {mutation.error && <p className="errors" role="alert">{mutation.error.message}</p>}

      <button className="button" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
        {mutation.isPending ? '요청 중…' : '광고 만들기'}
      </button>
    </section>
  )
}
