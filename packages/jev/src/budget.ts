/**
 * Input budget for one System One call.
 *
 * The provider documents a 1 MiB request ceiling, but the decision model behind it has a much
 * smaller effective input budget: measured against this profile's own ledger, requests whose text
 * stayed at or below 12,003 characters were accepted, while 12,015 characters were rejected with
 * `JEV_UPSTREAM_REJECTED` ("upstream rejected the content or input length"). Characters are a poor
 * proxy across scripts -- 12,000 Latin characters are roughly 3,000 tokens, while 12,000 CJK
 * characters are roughly 12,000 -- so the guard estimates tokens instead.
 */
import type { Json, JevQuestion, JevRequest } from './types.ts'

/**
 * Estimated tokens one request may carry.
 *
 * Sized just under the measured acceptance boundary for Latin text (12,000 characters ≈ 3,000
 * tokens) so a request that previously worked still fits, while a script-dense request that the
 * provider would reject is stopped locally instead of returning a 422.
 */
export const DEFAULT_MAX_INPUT_TOKENS = 2_800
/** Options one choice question may carry here; the protocol allows 255, but a long option set is a large request. */
export const MAX_CHOICE_OPTIONS_PER_QUESTION = 64

/**
 * Estimate the model tokens a string costs.
 *
 * Deliberately conservative and script-aware: one token per CJK/kana/Hangul code point, one per
 * four other characters. It is an estimate, not a tokenizer -- the point is to catch the order of
 * magnitude difference between a Latin and a CJK request before the provider does.
 */
export function estimateTokens(text: string): number {
  let tokens = 0
  for (const character of text) {
    const code = character.codePointAt(0) ?? 0
    if (code < 0x2e80 || (code >= 0xfb00 && code < 0xff00)) tokens += 0.25
    else tokens += 1
  }
  return tokens
}

/** Estimated tokens for every string inside one JSON value, keys excluded. */
function valueTokens(value: Json | undefined): number {
  if (value === null || value === undefined) return 0
  if (typeof value === 'string') return estimateTokens(value)
  if (typeof value === 'number' || typeof value === 'boolean') return 1
  if (Array.isArray(value)) return value.reduce<number>((sum, item) => sum + valueTokens(item as Json), 0)
  return Object.values(value).reduce<number>((sum, item) => sum + valueTokens(item as Json), 0)
}

/** Estimated tokens for the whole request: state, question prompts, option descriptions, criteria. */
export function requestTokens(request: JevRequest): number {
  let tokens = valueTokens(request.state)
  for (const question of request.questions) {
    tokens += valueTokens(question.prompt)
    if (question.kind === 'choice') {
      for (const option of question.options) tokens += valueTokens(option.description)
    } else if (question.kind === 'score') {
      for (const level of question.levels) tokens += valueTokens(level)
    } else if (question.kind === 'noul' && question.criteria !== undefined) {
      tokens += valueTokens(question.criteria.true as Json)
      tokens += valueTokens(question.criteria.false as Json)
    }
  }
  return tokens
}

/** The first choice question whose option set exceeds the local cap, or undefined. */
export function oversizedQuestion(questions: readonly JevQuestion[]): Extract<JevQuestion, { kind: 'choice' }> | undefined {
  return questions.find((question): question is Extract<JevQuestion, { kind: 'choice' }> =>
    question.kind === 'choice' && question.options.length > MAX_CHOICE_OPTIONS_PER_QUESTION)
}
