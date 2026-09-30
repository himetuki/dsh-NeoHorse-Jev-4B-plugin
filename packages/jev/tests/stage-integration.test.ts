/** Cold DSH history, native page authorization, and localhost Jev over a full step. */
import { createServer } from 'node:http'
import { mkdtemp, mkdir, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import AgentRegistry from '@deepseek-ai/dsh-agent'
import SessionController from '@deepseek-ai/dsh-api-session-controller'
import LlmRuntime, { createAssistantMessage, createToolResultMessage, createUserMessage, ToolCallId } from '@deepseek-ai/dsh-llm'
import SessionStore, { Session, SessionId } from '@deepseek-ai/dsh-session'
import JsonlPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import SessionQueryEngine from '@deepseek-ai/dsh-session-query'
import Storage from '@deepseek-ai/dsh-storage'
import { JsonStorageBackend } from '@deepseek-ai/dsh-storage-json'
import { DomainFacility } from '@deepseek-ai/dsh-storage-domain'
import UserQuestions from '@deepseek-ai/dsh-user-questions'
import JevService from '../src/index.ts'
import * as StageNavigation from '../src/stage-navigation.ts'

class ColdQuery extends SessionQueryEngine {
  override searchSessions(): Promise<never> { return Promise.reject(new Error('Search is outside this fixture')) }
  override searchEvents(): Promise<never> { return Promise.reject(new Error('Search is outside this fixture')) }
}

const cleanups: Array<() => Promise<void>> = []
afterEach(async () => {
  const failures: unknown[] = []
  for (const cleanup of cleanups.splice(0).reverse()) {
    try { await cleanup() } catch (error) { failures.push(error) }
  }
  vi.restoreAllMocks()
  if (failures.length > 0) throw new AggregateError(failures, 'Stage integration cleanup failed')
})

async function persistedSession(root: string): Promise<{ id: string; cursor: number }> {
  const context = new Context()
  await context.plugin(JsonlPersistence, { root: join(root, 'sessions') })
  const id = SessionId('stage-integration-cold')
  const session = Session.create(id, undefined, {
    version: 4, id, createdAt: Date.now(), cwd: join(root, 'workspace'), isSeeded: false,
  })
  const emit = (turn: number, step: number, content: Parameters<typeof createAssistantMessage>[0]['content']) => {
    session.append('assistant/message', { turn, step, stream: [],
      message: createAssistantMessage({ source: { provider: 'stage-fixture', model: 'recorded' }, content }),
    }, { surfaceOp: 'append' })
  }
  const callA = ToolCallId('stage-first-a')
  const callB = ToolCallId('stage-first-b')
  session.append('turn/start', { turn: 1 })
  session.append('step/start', { turn: 1, step: 1 })
  session.append('user/message', createUserMessage({ source: { kind: 'user' }, content: [{ type: 'text',
    text: 'Review the stage fixture. Fake secret: sk-0123456789abcdefghijklmnopqrstuvwxyz',
  }] }), { surfaceOp: 'append' })
  emit(1, 1, [
    ...Array.from({ length: 17 }, (_, index) => ({ type: 'reasoning' as const, text: `STAGE_T1S1 Think ${index + 1}` })),
    { type: 'text', text: 'STAGE_T1S1 two probes' },
    { type: 'tool-call', id: callA, name: 'stage_probe', arguments: '{"id":"a"}' },
    { type: 'tool-call', id: callB, name: 'stage_probe', arguments: '{"id":"b"}' },
  ])
  for (const [id, marker] of [[callA, 'a'], [callB, 'b']] as const) {
    session.append('tool/call', { turn: 1, step: 1, callId: id, name: 'stage_probe', arguments: `{"id":"${marker}"}` })
    session.append('tool/result', { turn: 1, step: 1,
      message: createToolResultMessage({ callId: id, content: [{ type: 'text', text: `probe ${marker} done` }], isError: false }),
    }, { surfaceOp: 'append' })
  }
  session.append('step/end', { turn: 1, step: 1 })
  session.append('step/start', { turn: 1, step: 2 })
  emit(1, 2, [{ type: 'text', text: 'STAGE_T1S2 Final response without tools' }])
  session.append('step/end', { turn: 1, step: 2 })
  session.append('turn/end', { turn: 1, reason: { kind: 'completed' } })
  session.append('turn/start', { turn: 2 })
  session.append('step/start', { turn: 2, step: 1 })
  session.append('user/message', createUserMessage({ source: { kind: 'user' }, content: [{ type: 'text',
    text: 'Inspect the cancelled fixture turn.',
  }] }), { surfaceOp: 'append' })
  emit(2, 1, [{ type: 'text', text: 'STAGE_T2S1 Tool failed before cancellation' }])
  session.append('step/end', { turn: 2, step: 1 })
  session.append('turn/end', { turn: 2, reason: { kind: 'aborted', reason: { kind: 'user' } } })
  const writer = await context.sessionPersistence.create(session.header)
  try {
    await writer.append(session.snapshotEvents())
    await writer.flush()
  } finally {
    await writer.close()
    await context.fiber.dispose()
  }
  return { id, cursor: session.seq - 1 }
}

async function host(root: string, endpoint: string): Promise<{ ctx: Context; controller: SessionController }> {
  const ctx = new Context()
  cleanups.push(() => ctx.fiber.dispose())
  await ctx.plugin(SessionStore)
  await ctx.plugin(AgentRegistry)
  await ctx.plugin(LlmRuntime)
  await ctx.plugin(SessionProjectionRegistry)
  new ColdQuery(ctx)
  await ctx.plugin(JsonlPersistence, { root: join(root, 'sessions') })
  await ctx.plugin(Storage)
  await ctx.plugin(UserQuestions)
  ctx.storage.backend.register('json', new JsonStorageBackend(join(root, 'storage')))
  ctx.provide('storageDomain', new DomainFacility(ctx, { backend: 'json' }))
  ctx.provide('profileContext', { dir: join(root, 'profile') } as never)
  ctx.provide('settings', { configure: () => () => {} } as never)
  ctx.provide('credentials', { resolve: async () => ({ value: 'localhost-stage-fixture', source: 'fixture' }) } as never)
  ctx.provide('typert', { lookups: { configure: () => () => {} }, contexts: { configureHost: () => () => {} } } as never)
  ctx.provide('agentDefaultModel', { currentSelection: () => ({ provider: 'fixture', model: 'fixture' }) } as never)
  ctx.provide('attachments', { imageLimits: {}, admitPromptContent: async (content: unknown[]) => content } as never)
  ctx.provide('fileUploads', { registerAgentResolver: () => () => {}, resolve: () => undefined,
    bindPrompt: () => ({ commit: () => {}, [Symbol.dispose]: () => {} }), retirePrompt: () => {} } as never)
  const controller = new SessionController(ctx, { nativeOpen: false })
  await ctx.plugin(JevService, { baseUrl: endpoint, model: 'stage-fixture', credentialRef: 'STAGE_FIXTURE_KEY',
    timeoutMs: 10_000, features: { 'stage-navigation': true } })
  const loaderExport = (StageNavigation as typeof StageNavigation & { default?: typeof StageNavigation.apply }).default ?? StageNavigation
  await ctx.plugin(loaderExport)
  return { ctx, controller }
}

it('uses the pinned native history page and persists one Jev result per complete cold step', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'jev-stage-integration-'))
  cleanups.push(() => rm(dir, { recursive: true, force: true }))
  await mkdir(join(dir, 'workspace'))
  const seeded = await persistedSession(dir)
  const calls: unknown[] = []
  const server = createServer(async (request, response) => {
    const chunks: Buffer[] = []
    for await (const chunk of request) chunks.push(Buffer.from(chunk))
    const wire = JSON.parse(Buffer.concat(chunks).toString()) as { state: { target: { step: number } }; questions: Record<string, { criteria: Record<string, string> }> }
    calls.push(wire)
    const options = Object.keys(wire.questions.stage!.criteria)
    const choice = wire.state.target.step === 1 ? 'implementation' : 'delivery_finalization'
    const probabilities = Object.fromEntries(options.map(option => [option, option === choice ? 0.45 : 0.55 / (options.length - 1)]))
    response.writeHead(200, { 'content-type': 'application/json' })
    response.end(JSON.stringify({ model: 'stage-fixture-system-one', answers: { stage: { choice, confidence: 0.45, probabilities } } }))
  })
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
  cleanups.push(async () => { server.closeAllConnections(); await new Promise<void>(resolve => server.close(() => resolve())) })
  const address = server.address()
  if (address === null || typeof address === 'string') throw new Error('Fixture server did not bind')
  const endpoint = `http://127.0.0.1:${address.port}/v1/systemone/stage`
  const first = await host(dir, endpoint)
  const nativePage = vi.spyOn(first.controller, 'page')
  const signal = new AbortController().signal
  const before = await first.ctx.jev.getStageNavigation(seeded.id, signal)
  expect(before.cursor).toBe(seeded.cursor)
  expect(before.turns.map(turn => [turn.turn, turn.steps.length, turn.reason?.kind])).toEqual([
    [1, 2, 'completed'], [2, 1, 'aborted'],
  ])
  expect(nativePage).toHaveBeenCalledWith({ address: { kind: 'session', sessionId: seeded.id },
    throughSeq: seeded.cursor, maxMessages: 1 }, signal)
  expect(calls).toHaveLength(0)
  const batch = await first.ctx.jev.startStageAnalysis({ sessionId: seeded.id, scope: { kind: 'turn', turn: 1 }, mode: 'missing' })
  expect(batch.total).toBe(2)
  await vi.waitFor(async () => {
    const snapshot = await first.ctx.jev.getStageNavigation(seeded.id, signal)
    expect(snapshot.batch?.status).toBe('completed')
    expect(snapshot.turns[0]?.steps.map(step => step.analysis.status)).toEqual(['succeeded', 'succeeded'])
  })
  expect(calls).toHaveLength(2)
  const firstStep = (await first.ctx.jev.getStageNavigation(seeded.id, signal)).turns[0]!.steps[0]!
  expect(firstStep.tools).toHaveLength(2)
  expect(firstStep.analysis).toMatchObject({ label: 'implementation', confidence: 0.45, model: 'stage-fixture-system-one' })
  const detail = await first.ctx.jev.getStageAnalysisRecord(seeded.id, firstStep.id)
  expect(detail?.request?.state).toMatchObject({ target: { step: 1 } })
  expect(JSON.stringify(detail?.request)).not.toContain('sk-0123456789abcdefghijklmnopqrstuvwxyz')
  expect(detail?.rawResponse).toMatchObject({ answers: { stage: { choice: 'implementation' } } })
  expect((detail?.request?.state as { target: { assistant: Array<{ content: unknown[] }>; tools: unknown[] } }).target.assistant[0]?.content).toHaveLength(18)
  expect((detail?.request?.state as { target: { assistant: unknown[]; tools: unknown[] } }).target.tools).toHaveLength(2)
  const repeat = await first.ctx.jev.startStageAnalysis({ sessionId: seeded.id, scope: { kind: 'turn', turn: 1 }, mode: 'missing' })
  expect(repeat.total).toBe(0)
  expect(calls).toHaveLength(2)
  await expect(first.ctx.jev.getStageNavigation('missing-session', signal)).rejects.toThrow()
  expect(calls).toHaveLength(2)
  await first.ctx.fiber.dispose()
  const second = await host(dir, endpoint)
  const afterRestart = await second.ctx.jev.getStageNavigation(seeded.id, signal)
  expect(afterRestart.turns[0]?.steps.map(step => step.analysis.status)).toEqual(['succeeded', 'succeeded'])
  expect(calls).toHaveLength(2)
})

it('stops a multi-step batch when the localhost service reports exhausted quota', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'jev-stage-quota-'))
  cleanups.push(() => rm(dir, { recursive: true, force: true }))
  await mkdir(join(dir, 'workspace'))
  const seeded = await persistedSession(dir)
  let requests = 0
  const server = createServer(async (request, response) => {
    for await (const _chunk of request) { /* Drain the local request before replying. */ }
    requests++
    response.writeHead(429, { 'content-type': 'application/json' })
    response.end(JSON.stringify({ error: 'Fixture quota exhausted' }))
  })
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
  cleanups.push(async () => { server.closeAllConnections(); await new Promise<void>(resolve => server.close(() => resolve())) })
  const address = server.address()
  if (address === null || typeof address === 'string') throw new Error('Fixture server did not bind')
  const { ctx } = await host(dir, `http://127.0.0.1:${address.port}/v1/systemone/stage`)
  const started = await ctx.jev.startStageAnalysis({ sessionId: seeded.id, scope: { kind: 'turn', turn: 1 }, mode: 'missing' })
  expect(started.total).toBe(2)
  await vi.waitFor(async () => {
    const snapshot = await ctx.jev.getStageNavigation(seeded.id, new AbortController().signal)
    expect(snapshot.batch?.status).toBe('failed')
  })
  expect(requests).toBe(1)
})
