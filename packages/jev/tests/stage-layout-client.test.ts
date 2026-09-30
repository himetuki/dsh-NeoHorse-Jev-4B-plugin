/** Stage runs follow native step adjacency and the saved Jev result. */

import { describe, expect, it } from 'vitest'
import type { StageAnalysisSummary, StageStep, StageTurn } from '../src/stage-types.ts'
import { stageNavigationItems } from '../src/client/stage-layout.ts'

function step(number: number, analysis: StageAnalysisSummary, status: StageStep['status'] = 'complete'): StageStep {
  return {
    id: `session:step-start-${number}`, turn: 8, step: number, startSeq: number * 10,
    endSeq: status === 'complete' ? number * 10 + 9 : undefined,
    status, classifiable: status !== 'in-progress', materialStatus: status === 'in-progress' ? 'IN_PROGRESS' : 'ready',
    messages: [{ seq: number * 10 + 1, content: [{ type: 'text', text: `Recorded output ${number}` }], interrupted: false }],
    assistant: { seq: number * 10 + 1, content: [{ type: 'text', text: `Recorded output ${number}` }], interrupted: false },
    tools: [], attemptSeqs: [], analysis,
  }
}

function turn(steps: StageStep[], id = 'session:turn-8'): StageTurn {
  return { id, turn: 8, startSeq: 1, endSeq: 200, requests: [{ seq: 1, content: [{ type: 'text', text: 'Build and inspect the result' }] }], steps }
}

const implementation: StageAnalysisSummary = { status: 'succeeded', label: 'implementation', confidence: 0.45 }
const review: StageAnalysisSummary = { status: 'succeeded', label: 'review_validation', confidence: 0.57 }

describe('stage navigation runs', () => {
  it('keeps repeated implementation after review as a separate selectable run', () => {
    const steps = Array.from({ length: 14 }, (_, index) => step(index + 1, index === 11 ? review : implementation))
    const items = stageNavigationItems(turn(steps))
    expect(items.map(item => item.kind === 'segment' ? [item.segment.label, item.segment.steps.map(value => value.step)] : item.kind)).toEqual([
      ['implementation', [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]],
      ['review_validation', [12]],
      ['implementation', [13, 14]],
    ])
    expect(items[0]!.id).not.toBe(items[2]!.id)
    expect(items[0]!.id).toContain('step-start-1')
    expect(items[2]!.id).toContain('step-start-13')
  })

  it('breaks runs across a missing native step, failed, stale, and live steps', () => {
    const items = stageNavigationItems(turn([
      step(1, implementation), step(3, implementation),
      step(4, { status: 'failed', failure: { code: 'TIMEOUT', message: 'Timed out' } }),
      step(5, implementation), step(6, { status: 'stale', label: 'implementation' }),
      step(7, implementation, 'in-progress'), step(8, implementation, 'terminal-partial'),
    ]))
    expect(items.map(item => item.kind)).toEqual(['segment', 'segment', 'gap', 'segment', 'gap', 'gap', 'segment'])
    expect(items.at(-1)).toMatchObject({ kind: 'segment', segment: { label: 'implementation' } })
  })

  it('does not merge equal labels across turns or depend on visible row numbers', () => {
    const first = stageNavigationItems(turn([step(13, implementation)], 'session:turn-8'))
    const second = stageNavigationItems(turn([step(13, implementation)], 'session:turn-9'))
    expect(first[0]!.id).not.toBe(second[0]!.id)
    const withOlderHistory = stageNavigationItems(turn([step(1, review), step(13, implementation)], 'session:turn-8'))
    expect(withOlderHistory[1]!.id).toBe(first[0]!.id)
  })
})
