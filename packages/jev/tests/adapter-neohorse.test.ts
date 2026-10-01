import { createServer, type IncomingMessage, type ServerResponse } from 'node:http'
import { afterEach, describe, expect, it } from 'vitest'
import { JEV_PROVIDER, JevAdapter, type JevConnection } from '../src/adapter.ts'
import type { JevQuestion, JevRequest } from '../src/types.ts'

const cleanups: Array<() => Promise<void>> = []
afterEach(async () => {
  const failures: unknown[] = []
  for (const cleanup of cleanups.splice(0).reverse()) {
    try { await cleanup() } catch (error) { failures.push(error) }
  }
  if (failures.length) throw new AggregateError(failures, 'NeoHorse adapter fixture cleanup failed')
})

type Reply = (body: Record<string, unknown>, call: number) => { status?: number; payload: unknown }

async function fixture(reply: Reply) {
  const received: Record<string, unknown>[] = []
  const server = createServer(async (request: IncomingMessage, response: ServerResponse) => {
    const chunks: Buffer[] = []
    for await (const chunk of request) chunks.push(Buffer.from(chunk))
    const body = JSON.parse(Buffer.concat(chunks).toString('utf8')) as Record<string, unknown>
    received.push(body)
    const answer = reply(body, received.length)
    response.writeHead(answer.status ?? 200, { 'content-type': 'application/json' })
    response.end(JSON.stringify(answer.payload))
  })
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
  const address = server.address()
  if (address === null || typeof address === 'string') throw new Error('NeoHorse adapter fixture did not bind')
  cleanups.push(async () => { await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve())) })
  return { url: `http://127.0.0.1:${address.port}/v1/systemone`, received }
}

function connection(url: string): JevConnection {
  return { baseUrl: url, model: 'NeoHorse-Jev-4B', credentialRef: 'JEV_TEST_KEY', apiKey: 'sk_fixture_key', timeoutMs: 5_000 }
}

/** Drive the adapter exactly as JevService does: one issued nonce and one typed envelope. */
async function judge(url: string, request: JevRequest): Promise<Record<string, unknown>> {
  const adapter = new JevAdapter()
  const issued = adapter.issue(request, connection(url))
  let text: string | undefined
  try {
    for await (const chunk of adapter.stream({
      provider: JEV_PROVIDER, model: 'NeoHorse-Jev-4B',
      messages: [{ role: 'user', content: [{ type: 'text', text: issued.envelope }] }],
    })) {
      if (chunk.type === 'block-end' && chunk.block.type === 'text') text = chunk.block.text
    }
  } finally { issued.release() }
  if (text === undefined) throw new Error('NeoHorse adapter produced no text block')
  return JSON.parse(text) as Record<string, unknown>
}

const noul = (id: string): JevQuestion => ({ id, kind: 'noul', prompt: 'Ready?' })
const answerAll = (body: Record<string, unknown>): Record<string, unknown> =>
  Object.fromEntries(Object.keys(body.questions as Record<string, unknown>).map(id => [id, { noul: 0.5 }]))

describe('NeoHorse-Jev-4B System One adapter', () => {
  it('keeps a judgment of at most 16 questions in one call', async () => {
    const http = await fixture(body => ({ payload: { model: 'NeoHorse-Jev-4B', answers: answerAll(body), usage: { input_tokens: 7, output_tokens: 3 } } }))
    const request: JevRequest = { state: 'one batch', questions: [noul('a'), noul('b'), noul('c')] }
    const merged = await judge(http.url, request)
    expect(http.received).toHaveLength(1)
    expect(Object.keys(merged.answers as object)).toEqual(['a', 'b', 'c'])
    expect(merged.usage).toEqual({ input_tokens: 7, output_tokens: 3 })
  })

  it('splits 40 questions into ordered 16/16/8 calls and merges answers and usage', async () => {
    const http = await fixture(body => ({ payload: { model: 'NeoHorse-Jev-4B', answers: answerAll(body), usage: { input_tokens: 3, output_tokens: 1 } } }))
    const request: JevRequest = { state: 'batched', questions: Array.from({ length: 40 }, (_, index) => noul(`question-${index}`)) }
    const merged = await judge(http.url, request)
    expect(http.received.map(body => Object.keys(body.questions as object).length)).toEqual([16, 16, 8])
    expect(Object.keys(merged.answers as object)).toHaveLength(40)
    expect(Object.keys(merged.answers as object)[0]).toBe('question-0')
    expect(Object.keys(merged.answers as object).at(-1)).toBe('question-39')
    expect(merged.usage).toEqual({ input_tokens: 9, output_tokens: 3 })
    expect(merged.model).toBe('NeoHorse-Jev-4B')
  })

  it('fails before dispatch when one request body exceeds the provider 1 MiB limit', async () => {
    const http = await fixture(() => ({ payload: { answers: {} } }))
    const request: JevRequest = { state: 'x'.repeat(1_200_000), questions: [noul('only')] }
    await expect(judge(http.url, request)).rejects.toMatchObject({
      code: 'BAD_REQUEST', message: expect.stringContaining('1 MiB'),
    })
    expect(http.received).toHaveLength(0)
  })

  it('keeps the provider code, message, and traceId on a refused request', async () => {
    const http = await fixture(() => ({ status: 403, payload: { code: 'NOT_IN_GRAYSCALE', message: '账号不在灰度名单', traceId: 'trace-abc-123' } }))
    const failure = await judge(http.url, { state: 'probe', questions: [noul('ready')] }).catch((error: unknown) => error as Error & { code?: string })
    expect(failure.code).toBe('AUTH')
    expect(failure.message).toContain('NOT_IN_GRAYSCALE')
    expect(failure.message).toContain('trace-abc-123')
    expect(failure.message).toContain('403')
  })

  it('redacts credential-shaped provider text before it can reach a record', async () => {
    const http = await fixture(() => ({ status: 401, payload: { code: 'BAD_KEY', message: 'Incorrect API key sk_tr_FAKEFIXTURE000000 provided', traceId: 'trace-1' } }))
    const failure = await judge(http.url, { state: 'probe', questions: [noul('ready')] }).catch((error: unknown) => error as Error)
    expect(failure.message).not.toContain('FAKEFIXTURE000000')
    expect(failure.message).toContain('[redacted-key]')
    expect(failure.message).toContain('trace-1')
  })
})
