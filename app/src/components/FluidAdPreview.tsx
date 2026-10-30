import { useLayoutEffect, useRef, useState, type ComponentProps } from 'react'
import { CANVAS } from '../config'
import AdCanvas from '../renderer/AdCanvas'

type Props = Omit<ComponentProps<typeof AdCanvas>, 'previewScale'> & { className?: string }

// 부모 너비에 맞춰 축소 비율을 정한다. 원본 1080×1350 DOM은 그대로라 PNG 출력에 영향 없음
export default function FluidAdPreview({ className, ...canvas }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)

  useLayoutEffect(() => {
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    observer.observe(ref.current!)
    return () => observer.disconnect()
  }, [])

  return (
    <div ref={ref} className={className ? `fluid-ad ${className}` : 'fluid-ad'}>
      {width > 0 && <AdCanvas {...canvas} previewScale={width / CANVAS.width} />}
    </div>
  )
}
