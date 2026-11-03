export const EMOJI_LEVELS = ['없음', '적음', '많음'] as const
export type EmojiLevel = (typeof EMOJI_LEVELS)[number]

const GUIDE: Record<EmojiLevel, string> = {
  없음: '게시글 본문에 이모티콘을 쓰지 않음',
  적음: '게시글 본문에 이모티콘을 1~2개만 사용',
  많음: '게시글 본문의 문단마다 이모티콘을 여러 개 사용',
}

// 합성 폰트에 이모지 글자가 없어 이미지에 올라가는 문구에는 쓰지 않게 한다 (COMPOSITION_GLYPH_MISSING)
// shortcut: 텍스트 스키마(ProductInput)에 이모티콘 항목이 없어 자유 문자열인 광고 목적에 붙인다, 필드가 생기면 그 필드로 옮긴다
export const withEmojiGuide = (purpose: string, level: EmojiLevel) =>
  `${purpose} (${GUIDE[level]}, 헤드라인·서브 문구·CTA에는 이모티콘 금지)`
