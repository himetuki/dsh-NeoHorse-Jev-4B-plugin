/** Deterministic local System One fixture; never forwards a request. */
import { createServer } from 'node:http'
import { appendFileSync } from 'node:fs'

const port = Number(process.env.JEV_EVAL_MOCK_JEV_PORT ?? '45454')
const evidence = process.env.JEV_EVAL_MOCK_JEV_LOG
const mode = process.env.JEV_EVAL_MOCK_JEV_MODE ?? 'normal'

createServer(async (request, response) => {
  if (request.method !== 'POST' || request.url !== '/v1/systemone') {
    response.writeHead(404).end()
    return
  }
  let body = ''
  for await (const chunk of request) body += chunk.toString()
  const input = JSON.parse(body)
  if (evidence) appendFileSync(evidence, JSON.stringify({ model: input.model, questions: Object.keys(input.questions ?? {}) }) + '\n')
  const answers = {}
  for (const [id, question] of Object.entries(input.questions ?? {})) {
    if (question.type === 'choice') {
      const options = Object.keys(question.criteria ?? {})
      const choice = options.includes('omit') ? 'omit'
        : mode === 'completion-omission' && options.includes('omission') ? 'omission'
        : options.includes('complete') ? 'complete' : options[0]
      answers[id] = { type: 'choice', choice, confidence: 0.99 }
    } else if (question.type === 'score') answers[id] = { type: 'score', score: 0, confidence: 0.99 }
    else answers[id] = { type: 'noul', noul: 0.99 }
  }
  response.writeHead(200, { 'content-type': 'application/json' })
  response.end(JSON.stringify({ answers, usage: { input_tokens: 4, output_tokens: 2 } }))
}).listen(port, '127.0.0.1')
