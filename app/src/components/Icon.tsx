// Material Symbols 아이콘 (장식용, 스크린리더에서는 숨김)
export default function Icon({ name, fill, className }: { name: string; fill?: boolean; className?: string }) {
  return (
    <span className={className ? `icon ${className}` : 'icon'} aria-hidden="true"
      style={fill ? { fontVariationSettings: "'FILL' 1" } : undefined}>
      {name}
    </span>
  )
}
