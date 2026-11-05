/** Text Owner #25 v0.10 canonical three-level preference. */
export const EMOJI_LEVELS=['없음','보통','많이'] as const
export type EmojiLevel=(typeof EMOJI_LEVELS)[number]
// Old FE #22 sessionStorage used 적음/많음. Explicit compatibility only;
// new requests and visible choices are Owner's actual vocabulary.
export const toOwnerEmojiLevel=(value:EmojiLevel|'적음'|'많음'):EmojiLevel=>
  value==='적음'?'보통':value==='많음'?'많이':value
