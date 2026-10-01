/** Stop a headless evaluation as soon as native human input is requested. */
import { appendFileSync, writeFileSync } from 'node:fs'

export const name = 'eval-interaction-guard'
export const inject = ['llm', 'jev']

export function apply(ctx) {
  const marker = process.env.JEV_EVAL_READY_MARKER
  if (marker) {
    const features = Object.fromEntries([
      'skill-selection', 'file-ranking', 'drift-monitoring', 'completion-check', 'stage-navigation',
      'goal-supervision', 'instruction-guidance', 'interjection-routing',
      'shared-findings', 'output-admission', 'test-log-admission', 'workspace-approval',
    ].map(id => [id, ctx.jev.isFeatureEnabled(id)]))
    writeFileSync(marker, JSON.stringify({ features, at: new Date().toISOString() }) + '\n')
  }
  const checked = new Set()
  ctx.on('agent/pre-step', async ({ agent }, next) => {
    if (!checked.has(agent.id)) {
      const provider = process.env.JEV_EVAL_PROVIDER
      const model = process.env.JEV_EVAL_MODEL
      const expected = Number(process.env.JEV_EVAL_CONTEXT_WINDOW)
      const info = await ctx.llm.resolveModelInfo(provider, model)
      if (info.context?.contextWindow !== expected) {
        throw new Error(`Jev evaluation context capacity differs from frozen ${expected}`)
      }
      checked.add(agent.id)
    }
    return next()
  }, { prepend: true })
  for (const event of ['user-questions/request', 'approval/request']) {
    ctx.on(event, async (request, next) => {
      const agent = request.agent
      const marker = process.env.JEV_EVAL_INTERACTIONS
      if (marker) appendFileSync(marker, JSON.stringify({ event, sessionId: agent?.session?.id ?? null, at: new Date().toISOString() }) + '\n')
      if (agent?.status === 'running') queueMicrotask(() => agent.cancel({ kind: 'user' }))
      if (event === 'user-questions/request') {
        try { return await next() } catch (cause) {
          const error = new Error('ask_user_question was aborted before the user answered', { cause })
          error.name = 'UserQuestionError'
          error.code = 'ASK_ABORTED'
          throw error
        }
      }
      return next()
    }, { prepend: true })
  }
}
