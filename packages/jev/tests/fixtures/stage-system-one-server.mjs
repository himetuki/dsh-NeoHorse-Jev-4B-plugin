/** Test-only localhost System One endpoint for the stage-navigation profile. */
import { appendFile, mkdir } from 'node:fs/promises'
import { createServer } from 'node:http'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../../..')
const artifacts = join(root, '.artifacts/stage-validation')
const requiredHome = join(artifacts, 'home')
if (resolve(process.env.DSH_HOME ?? '') !== requiredHome) {
  throw new Error(`Set DSH_HOME=${requiredHome}; refusing to serve outside the isolated fixture home`)
}
await mkdir(artifacts, { recursive: true })
const logPath = join(artifacts, 'system-one-requests.jsonl')
const known = new Map([
  ['1:1', { choice: 'implementation', confidence: 0.92 }],
  ['1:2', { choice: 'implementation', confidence: 0.45 }],
  ['2:1', { choice: 'review_validation', confidence: 0.64 }],
  ['2:2', { choice: 'delivery_finalization', confidence: 0.88 }],
  ['3:1', { choice: 'implementation', confidence: 0.52 }],
  ['4:1', { choice: 'unknown', confidence: 0.31 }],
])
const calls = []
const held = new Set()
let serial = 0

function stageMarker(body) {
  const hits = [...JSON.stringify(body.state ?? {}).matchAll(/STAGE_T(\d+)S(\d+)/g)]
  const last = hits.at(-1)
  return last === undefined ? undefined : `${last[1]}:${last[2]}`
}

function answerFor(question, selected, confidence) {
  if (question?.type === 'choice') {
    const options = Object.keys(question.criteria ?? {})
    if (!options.includes(selected)) throw new Error(`stage choice ${selected} absent from ${options.join(', ')}`)
    const remainder = options.length > 1 ? (1 - confidence) / (options.length - 1) : 0
    return { choice: selected, confidence,
      probabilities: Object.fromEntries(options.map(option => [option, option === selected ? confidence : remainder])) }
  }
  if (question?.type === 'score') {
    const levels = question.criteria?.length ?? 0
    return { score: 0, probabilities: Object.fromEntries(Array.from({ length: levels }, (_, index) => [String(index), index === 0 ? 1 : 0])) }
  }
  if (question?.type === 'noul') return { noul: 0.5 }
  throw new Error(`Unsupported fixture question type: ${String(question?.type)}`)
}

function json(response, status, value) {
  response.writeHead(status, { 'content-type': 'application/json' })
  response.end(JSON.stringify(value))
}

const server = createServer(async (request, response) => {
  const path = new URL(request.url ?? '/', 'http://127.0.0.1').pathname
  if (request.method === 'GET' && path === '/stats') {
    json(response, 200, { count: calls.length, pending: held.size,
      calls: calls.map(({ id, mode, marker, selected, redacted, status }) => ({ id, mode, marker, selected, redacted, status })) })
    return
  }
  if (request.method === 'GET' && path === '/dump') {
    json(response, 200, calls)
    return
  }
  if (request.method === 'POST' && path === '/reset') {
    calls.length = 0
    json(response, 200, { reset: true })
    return
  }
  if (request.method === 'POST' && path === '/release') {
    for (const release of held) release()
    json(response, 200, { released: true })
    return
  }
  const mode = path.slice('/v1/systemone/stage-'.length)
  if (request.method !== 'POST' || !path.startsWith('/v1/systemone/stage-')
    || !['success', 'invalid', 'quota', 'held'].includes(mode)) {
    json(response, 404, { error: 'Unknown fixture path' })
    return
  }
  let body
  try {
    const chunks = []
    for await (const chunk of request) chunks.push(chunk)
    body = JSON.parse(Buffer.concat(chunks).toString('utf8'))
  } catch {
    json(response, 400, { error: 'Invalid fixture JSON' })
    return
  }
  const marker = stageMarker(body)
  const selected = known.get(marker)
  const entry = { id: ++serial, mode, marker, selected: selected?.choice,
    redacted: !JSON.stringify(body).includes('sk-0123456789abcdefghijklmnopqrstuvwxyz'),
    status: 'received', body }
  calls.push(entry)
  await appendFile(logPath, JSON.stringify(entry) + '\n')
  process.stderr.write(`stage fixture ${mode} call ${entry.id} marker ${marker ?? 'missing'}\n`)
  if (!entry.redacted) {
    entry.status = 'redaction-failed'
    json(response, 422, { error: 'Synthetic credential reached System One' })
    return
  }
  if (selected === undefined) {
    entry.status = 'marker-missing'
    json(response, 422, { error: 'Current complete step marker was not sent' })
    return
  }
  if (mode === 'quota') {
    entry.status = 'quota'
    json(response, 429, { error: 'Synthetic fixture quota exhausted' })
    return
  }
  if (mode === 'held') {
    entry.status = 'pending'
    await new Promise(resolve => {
      held.add(resolve)
      response.once('close', () => { held.delete(resolve); resolve() })
    })
    if (response.destroyed) {
      entry.status = 'cancelled'
      return
    }
  }
  try {
    const answers = Object.fromEntries(Object.entries(body.questions ?? {}).map(([id, question]) => [id,
      answerFor(question, selected.choice, selected.confidence)]))
    if (mode === 'invalid') {
      const id = Object.keys(answers)[0]
      if (id !== undefined) answers[id] = { choice: 'not_a_stage' }
    }
    entry.status = mode === 'invalid' ? 'invalid' : 'answered'
    json(response, 200, { model: 'stage-fixture-system-one', answers, usage: { input_tokens: 7, output_tokens: 3 } })
  } catch (error) {
    entry.status = 'fixture-error'
    json(response, 422, { error: error instanceof Error ? error.message : String(error) })
  }
})

server.listen(0, '127.0.0.1', () => {
  const address = server.address()
  if (address === null || typeof address === 'string') throw new Error('Fixture server did not bind')
  const base = `http://127.0.0.1:${address.port}`
  process.stdout.write(JSON.stringify({
    success: `${base}/v1/systemone/stage-success`,
    invalid: `${base}/v1/systemone/stage-invalid`,
    quota: `${base}/v1/systemone/stage-quota`,
    held: `${base}/v1/systemone/stage-held`,
    stats: `${base}/stats`, dump: `${base}/dump`, reset: `${base}/reset`, release: `${base}/release`, logPath,
  }) + '\n')
})

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.once(signal, () => {
    for (const release of held) release()
    server.close(() => process.exit(0))
  })
}
