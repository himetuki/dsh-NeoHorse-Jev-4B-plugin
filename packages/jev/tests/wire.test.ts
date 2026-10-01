import { describe, expect, it } from 'vitest'
import { parseWireResponse, validateRequest, wireBody } from '../src/wire.ts'
import type { JevRequest } from '../src/types.ts'

const request: JevRequest = {
  state: {},
  questions: [
    { id: 'route', kind: 'choice', prompt: { task: 'choose' }, options: [
      { id: 'left', description: { path: ['left'] } }, { id: 'right', description: null },
    ] },
    { id: 'risk', kind: 'score', prompt: 'How much risk?', levels: ['low', { risk: 'medium' }, 'high'] },
    { id: 'ready', kind: 'noul', prompt: ['Is it ready?'], criteria: { true: 'ready', false: 'not ready' } },
  ],
}

const response = {
  answers: {
    route: { choice: 'left', probabilities: { left: 0.7, right: 0.3 }, confidence: 0.8 },
    risk: { score: 1.5, probabilities: { '0': 0.1, '1': 0.4, '2': 0.5 }, legend: ['low', 'medium', 'high'] },
    ready: { noul: 0.65 },
  },
  usage: { input_tokens: 42 },
}

describe('System One typed exchange', () => {
  it('keeps structured criteria and a fractional score in its original rubric', () => {
    const body = wireBody('NeoHorse-Jev-4B', request)
    expect(body).toMatchObject({ state: {}, questions: {
      route: { type: 'choice', instructions: { task: 'choose' }, criteria: { left: { path: ['left'] }, right: null } },
      risk: { type: 'score', criteria: ['low', { risk: 'medium' }, 'high'] },
      ready: { type: 'noul', criteria: { true: 'ready', false: 'not ready' } },
    } })
    const result = parseWireResponse(response, request)
    expect(result.response.answers).toEqual([
      { id: 'route', kind: 'choice', optionId: 'left', probabilities: { left: 0.7, right: 0.3 }, confidence: 0.8 },
      { id: 'risk', kind: 'score', value: 1.5, probabilities: { '0': 0.1, '1': 0.4, '2': 0.5 }, legend: ['low', 'medium', 'high'] },
      { id: 'ready', kind: 'noul', probability: 0.65 },
    ])
    expect(result.usage).toEqual({ inputTokens: 42 })
  })

  it('rejects incomplete, wrong-kind, unknown-option, and out-of-rubric responses', () => {
    expect(() => parseWireResponse({ answers: { route: response.answers.route } }, request)).toThrow()
    expect(() => parseWireResponse({ ...response, answers: { ...response.answers, risk: { type: 'noul', score: 1.5 } } }, request)).toThrow()
    expect(() => parseWireResponse({ ...response, answers: { ...response.answers, route: { choice: 'other' } } }, request)).toThrow()
    expect(() => parseWireResponse({ ...response, answers: { ...response.answers, risk: { score: 2.5 } } }, request)).toThrow()
    expect(() => parseWireResponse({ ...response, answers: { ...response.answers, route: { choice: 'left', probabilities: {} } } }, request)).toThrow()
  })

  it('refuses bad questions before transport', () => {
    expect(() => validateRequest({ state: {}, questions: [] })).toThrow()
    expect(() => validateRequest({ state: {}, questions: [{ id: 'bad', kind: 'choice', prompt: 'pick', options: [] }] })).toThrow()
    expect(() => validateRequest({ state: {}, questions: [{ id: 'bad', kind: 'score', prompt: 'rate', levels: ['only'] }] })).toThrow()
  })
})
