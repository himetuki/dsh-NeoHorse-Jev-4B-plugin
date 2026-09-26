/** Test-only command for the original skill-catalog and glob host paths. */
import { randomUUID } from 'node:crypto'
import { agentEvents } from '@deepseek-ai/dsh-agent'
import { createUserMessage, ToolCallId } from '@deepseek-ai/dsh-llm'

export const name = 'jev-selection-fixture'
export const inject = ['tools', 'skills', 'commands']

const PROVIDER = 'jev-selection-fixture'
const USAGE = 'Use /jev_selection_fixture skills or /jev_selection_fixture files [glob pattern]'

export function apply(ctx) {
  ctx.effect(() => ctx.skills.registerProvider(() => ({
    name: PROVIDER,
    async list() {
      return Array.from({ length: 7 }, (_, index) => ({
        name: 'jev-qa-skill-' + (index + 1),
        description: 'Test skill ' + (index + 1) + ' for PDF document analysis',
        invocation: { modelInvocable: index !== 6, userInvocable: true },
        source: 'runtime', provider: PROVIDER, rank: 250, locator: index,
      }))
    },
    async get() { throw new Error('The catalog fixture must not load a skill body') },
  })))
  ctx.effect(() => ctx.commands.register({
    name: 'jev_selection_fixture',
    description: 'Exercise the original skill-catalog or glob selection hook without a main-model call',
    input: { hint: 'skills or files [glob pattern]' },
    async handler({ agent, signal, rawInput }) {
      const [kind, ...rest] = rawInput.trim().split(/\s+/)
      if (kind !== 'skills' && kind !== 'files') return { kind: 'error', text: USAGE }
      const intent = createUserMessage({ source: { kind: 'user' },
        content: [{ type: 'text', text: 'Find PDF document analysis material' }] })
      try {
        if (kind === 'skills') {
          const decision = await agentEvents(ctx, agent).waterfall(
            'agent/pre-step', { messages: [intent], turn: 1, step: 1, signal },
            () => Promise.resolve({ kind: 'enter', messages: [intent] }),
          )
          const catalog = decision.kind === 'enter'
            ? decision.messages.find(message => message.source.kind === 'jev-skill-catalog' || message.source.kind === 'skill-catalog')
            : undefined
          const text = catalog?.content.filter(block => block.type === 'text').map(block => block.text).join('\n') ?? ''
          return { kind: 'success', text: JSON.stringify({ source: catalog?.source, text, mainModelCalled: false }, null, 2) }
        }
        agent.session.append('user/message', intent, { surfaceOp: 'append' })
        const result = await ctx.tools.execute({
          callId: ToolCallId('jev-qa-' + randomUUID()), name: 'glob',
          arguments: { pattern: rest.join(' ') || '**/*' }, agent, signal,
        })
        const text = JSON.stringify({ value: result.value, content: result.content, mainModelCalled: false }, null, 2)
        return result.isError ? { kind: 'error', text } : { kind: 'success', text }
      } catch (error) {
        return { kind: 'error', text: error instanceof Error ? error.message : String(error) }
      }
    },
  }))
}
