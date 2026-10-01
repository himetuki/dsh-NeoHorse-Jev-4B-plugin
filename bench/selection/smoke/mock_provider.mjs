/** Stop after the first native model request and save its tool catalog. */
import { createRequire } from 'node:module'
import { createHash } from 'node:crypto'
import { writeFileSync } from 'node:fs'

const requireFromDsh = createRequire(process.env.DSH_PKG_JSON)
const { LlmAdapter, ReasoningEffortId } = await import(requireFromDsh.resolve('@deepseek-ai/dsh-llm'))

class CatalogAdapter extends LlmAdapter {
  async resolveModel(provider, model) {
    return { provider, id: model, name: model,
      context: { contextWindow: 1000000 },
      reasoning: { efforts: [{ id: ReasoningEffortId('high'), name: 'High' }], defaultEffort: ReasoningEffortId('high') } }
  }

  async * stream(options) {
    const tools = [...(options.tools ?? [])].sort((a, b) => a.name.localeCompare(b.name))
    writeFileSync(process.env.TOOLS_LOG, JSON.stringify({
      count: tools.length,
      names: tools.map(tool => tool.name),
      schema_sha256: createHash('sha256').update(JSON.stringify(tools)).digest('hex'),
    }) + '\n')
    yield { type: 'block-start', index: 0, blockType: 'text' }
    yield { type: 'text-delta', index: 0, text: 'Keyless catalog inspection complete.' }
    yield { type: 'block-end', index: 0, block: { type: 'text', text: 'Keyless catalog inspection complete.' } }
    yield { type: 'usage', usage: { inputTokens: 1, outputTokens: 1, cacheReadTokens: 0, cacheWriteTokens: 0 } }
    yield { type: 'finish', reason: { kind: 'stop' } }
  }
}

export const name = 'eval-mock-model'
export const inject = ['llm']
export function apply(ctx) { ctx.llm.registerAdapter(['eval-mock'], new CatalogAdapter()) }
