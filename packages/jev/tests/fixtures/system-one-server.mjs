/** Deterministic localhost-only System One server for test profiles. */
import { createServer } from 'node:http'

let invalidOnce = false
let calls = 0

const server = createServer(async (request, response) => {
  const path = new URL(request.url ?? '/', 'http://127.0.0.1').pathname
  if (request.method === 'POST' && path === '/reset') {
    invalidOnce = false
    calls = 0
    response.writeHead(200, { 'content-type': 'application/json' })
    response.end(JSON.stringify({ reset: true }))
    return
  }
  if (request.method !== 'POST' || !path.startsWith('/v1/systemone/')) {
    response.writeHead(404)
    response.end()
    return
  }
  let body
  try {
    const chunks = []
    for await (const chunk of request) chunks.push(chunk)
    body = JSON.parse(Buffer.concat(chunks).toString('utf8'))
  } catch {
    response.writeHead(400)
    response.end()
    return
  }
  calls += 1
  const questions = body?.questions ?? {}
  const answers = Object.fromEntries(Object.entries(questions).map(([id, question]) => {
    if (question?.type === 'choice') {
      const options = Object.keys(question.criteria ?? {})
      return [id, { choice: options[0], probabilities: Object.fromEntries(options.map(option => [option, 1 / options.length])) }]
    }
    if (question?.type === 'score') {
      const levels = question.criteria?.length ?? 0
      return [id, { score: (levels - 1) / 2, probabilities: Object.fromEntries(Array.from({ length: levels }, (_, index) => [String(index), 1 / levels])) }]
    }
    return [id, { noul: 0.75 }]
  }))
  const makeInvalid = path.endsWith('/always-invalid') || (path.endsWith('/invalid-once') && !invalidOnce)
  if (path.endsWith('/invalid-once')) invalidOnce = true
  if (makeInvalid) delete answers[Object.keys(answers)[0]]
  response.writeHead(200, { 'content-type': 'application/json' })
  response.end(JSON.stringify({ answers, usage: { input_tokens: 7, output_tokens: 3 } }))
  process.stderr.write(`fixture ${path} call ${calls}\n`)
})

server.listen(0, '127.0.0.1', () => {
  const address = server.address()
  if (address === null || typeof address === 'string') throw new Error('fixture server did not bind')
  process.stdout.write(`http://127.0.0.1:${address.port}/v1/systemone/success\n`)
  process.stdout.write(`http://127.0.0.1:${address.port}/v1/systemone/invalid-once\n`)
  process.stdout.write(`http://127.0.0.1:${address.port}/v1/systemone/always-invalid\n`)
})
