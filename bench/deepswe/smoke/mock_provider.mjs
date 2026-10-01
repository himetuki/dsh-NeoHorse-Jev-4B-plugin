/** Keyless DSH model fixture that makes one real bash call, then stops. */
import { createRequire } from 'node:module'
import { createHash } from 'node:crypto'
import { writeFileSync } from 'node:fs'

const requireFromDsh = createRequire(process.env.JEV_EVAL_DSH_PACKAGE_JSON)
const { LlmAdapter, ToolCallId, ReasoningEffortId } = await import(requireFromDsh.resolve('@deepseek-ai/dsh-llm'))
let modelCalls = 0

class EvalMockAdapter extends LlmAdapter {
  async resolveModel(provider, model) {
    return { provider, id: model, name: model,
      context: { contextWindow: Number(process.env.JEV_EVAL_CONTEXT_WINDOW) },
      reasoning: { efforts: [{ id: ReasoningEffortId('high'), name: 'High' }], defaultEffort: ReasoningEffortId('high') } }
  }

  async * stream(options) {
    modelCalls += 1
    if (modelCalls === 1 && process.env.JEV_EVAL_MOCK_TOOLS_LOG) {
      const tools = [...(options.tools ?? [])].sort((left, right) => left.name.localeCompare(right.name))
      writeFileSync(process.env.JEV_EVAL_MOCK_TOOLS_LOG, JSON.stringify({
        count: tools.length, names: tools.map(tool => tool.name),
        schema_sha256: createHash('sha256').update(JSON.stringify(tools)).digest('hex'),
      }) + '\n')
    }
    const toolResults = options.messages.flatMap(message => message.content ?? [])
      .filter(block => block.type === 'tool-result')
    if (modelCalls === 1) {
      const mode = process.env.JEV_EVAL_MOCK_SCENARIO ?? 'patch'
      const command = mode === 'long-log'
        ? "printf 'expected\\n' > answer.txt; for i in $(seq 1 800); do printf 'progress %04d\\n' \"$i\"; done"
        : "printf 'expected\\n' > answer.txt; printf 'wrote answer.txt\\n'"
      const args = JSON.stringify({ command, description: 'Implement the requested answer file and inspect command output.' })
      const id = ToolCallId('eval-mock-bash')
      yield { type: 'block-start', index: 0, blockType: 'tool-call' }
      yield { type: 'tool-call-delta', index: 0, id, name: 'bash', argumentsDelta: args }
      yield { type: 'block-end', index: 0, block: { type: 'tool-call', id, name: 'bash', arguments: args } }
      yield { type: 'usage', usage: { inputTokens: 11, outputTokens: 5, cacheReadTokens: 0, cacheWriteTokens: 0 } }
      yield { type: 'finish', reason: { kind: 'tool-calls' } }
      return
    }
    if (process.env.JEV_EVAL_MOCK_SCENARIO === 'long-log' && modelCalls === 2 && toolResults.length === 1) {
      const visible = toolResults[0].content?.filter(block => block.type === 'text').map(block => block.text).join('\n') ?? ''
      const match = /\[Jev original log: (\/tmp\/dsh-spill-[^\n]+?\.txt)\. /.exec(visible)
      if (match && !match[1].includes("'")) {
        const args = JSON.stringify({ command: `cat '${match[1]}'`, description: 'Read full original log through its recovery reference.' })
        const id = ToolCallId('eval-mock-readback')
        yield { type: 'block-start', index: 0, blockType: 'tool-call' }
        yield { type: 'tool-call-delta', index: 0, id, name: 'bash', argumentsDelta: args }
        yield { type: 'block-end', index: 0, block: { type: 'tool-call', id, name: 'bash', arguments: args } }
        yield { type: 'usage', usage: { inputTokens: 9, outputTokens: 5, cacheReadTokens: 0, cacheWriteTokens: 0 } }
        yield { type: 'finish', reason: { kind: 'tool-calls' } }
        return
      }
    }
    const reply = 'I wrote answer.txt and ran the command.'
    yield { type: 'block-start', index: 0, blockType: 'text' }
    yield { type: 'text-delta', index: 0, text: reply }
    yield { type: 'block-end', index: 0, block: { type: 'text', text: reply } }
    yield { type: 'usage', usage: { inputTokens: 8, outputTokens: 7, cacheReadTokens: 0, cacheWriteTokens: 0 } }
    yield { type: 'finish', reason: { kind: 'stop' } }
  }
}

export const name = 'eval-mock-model'
export const inject = ['llm']

export function apply(ctx) {
  ctx.llm.registerAdapter(['eval-mock'], new EvalMockAdapter())
}
