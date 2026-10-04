import { describe, expect, it } from 'vitest'
import { DEFAULT_MAX_INPUT_TOKENS, estimateTokens, MAX_CHOICE_OPTIONS_PER_QUESTION, oversizedQuestion, requestTokens } from '../src/budget.ts'
import type { JevRequest } from '../src/types.ts'

describe('input budget estimation', () => {
  it('counts Latin text at roughly four characters per token', () => {
    expect(estimateTokens('a'.repeat(400))).toBe(100)
  })

  it('counts CJK text at roughly one token per character', () => {
    // The provider's ceiling is a token ceiling: 12,000 CJK characters must not look as cheap as
    // 12,000 Latin characters, which is what a character budget would assume.
    expect(estimateTokens('判断'.repeat(200))).toBe(400)
    expect(estimateTokens('判断'.repeat(200))).toBeGreaterThan(estimateTokens('ab'.repeat(200)) * 3)
  })

  it('sums the state, prompts, and option descriptions', () => {
    const request: JevRequest = {
      state: { task: 'a'.repeat(400) },
      questions: [{ id: 'q', kind: 'choice', prompt: 'b'.repeat(40), options: [{ id: 'one', description: 'c'.repeat(40) }] }],
    }
    expect(requestTokens(request)).toBe(120)
  })

  it('ignores absent noul criteria and numbers cost one token each', () => {
    expect(requestTokens({ state: 1, questions: [{ id: 'q', kind: 'noul', prompt: 'ready?' }] })).toBe(2.5)
  })

  it('keeps the default budget under the measured acceptance boundary', () => {
    // 12,000 Latin characters were accepted and 12,015 rejected; the default must stay below that.
    expect(DEFAULT_MAX_INPUT_TOKENS).toBeLessThan(estimateTokens('x'.repeat(12_100)))
  })

  it('flags only choice questions above the local option cap', () => {
    const many = Array.from({ length: MAX_CHOICE_OPTIONS_PER_QUESTION + 1 }, (_, index) => ({ id: `line-${index}`, description: null }))
    const at = Array.from({ length: MAX_CHOICE_OPTIONS_PER_QUESTION }, (_, index) => ({ id: `line-${index}`, description: null }))
    expect(oversizedQuestion([{ id: 'many', kind: 'choice', prompt: 'pick', options: many }])?.id).toBe('many')
    expect(oversizedQuestion([{ id: 'at', kind: 'choice', prompt: 'pick', options: at }])).toBeUndefined()
    expect(oversizedQuestion([{ id: 'n', kind: 'noul', prompt: 'ready?' }])).toBeUndefined()
  })
})
