/** Test-only slash command that exercises the Jev consumer API in a real Web root Session. */
export const name = 'jev-test-command'
export const inject = ['jev', 'commands']

export function apply(ctx) {
  ctx.effect(() => ctx.jev.registerFeature({
    id: 'fixture',
    name: 'Jev test fixture / 测试夹具',
    description: 'Exercises common judgment only; performs no business action.',
  }))
  ctx.effect(() => ctx.commands.register({
    name: 'jev_fixture',
    description: 'Test-only typed Jev call / 仅测试 Jev 类型化判断',
    async handler({ agent, signal, rawInput }) {
      let version = 0
      const result = await ctx.jev.judge({
        featureId: 'fixture',
        agent,
        link: { sessionId: agent.session.id, runId: 'test-command' },
        signal,
        refresh: () => ({
          state: { fixture: 'jev-common-foundation', version: ++version },
          questions: [
            { id: 'route', kind: 'choice', prompt: 'Choose a fixed test route', options: [
              { id: 'left', description: 'test left' }, { id: 'right', description: 'test right' },
            ] },
            { id: 'risk', kind: 'score', prompt: 'Rate a fixed test risk', levels: ['low', 'medium', 'high'] },
            { id: 'ready', kind: 'noul', prompt: 'Is this a fixed test?' },
          ],
        }),
        interpret: () => rawInput.trim() === 'undetermined'
          ? { usable: false, reason: 'The test consumer declared this answer unusable.' }
          : { usable: true },
        canAdopt: () => rawInput.trim() === 'stale' ? 'The test target expired.' : true,
      })
      return { kind: 'success', text: `Jev fixture: ${result.kind}; operation ${result.operationId}; attempts ${version}` }
    },
  }))
}
