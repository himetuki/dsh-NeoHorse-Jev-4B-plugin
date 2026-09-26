# @dsh-jev/plugin

This package adds shared, typed Jev judgments to a DeepSeek Harness Web profile. It registers a Host service (`ctx.jev`), a plugin-owned Typert Remote namespace (`jev`), and one settings and records page. The package contains no business feature. Business plugins register a feature and decide whether a complete answer is useful or still current.

## Install and configure

Build this workspace, then install the package into an isolated DSH Web profile with the official `dsh plugin --profile <name> add <package-path>` command. Its `cordis.patch.yml` inserts the Host row with id `jev`; the package's Web Client mounts the generated Remote contribution and page. The profile must supply the standard LLM, credentials, user questions, settings, and storage domain services. This plugin requires DSH `0.1.7-rc.2` and Cordis `4.0.4`.

The Jev page edits the profile's `jev` configuration through DSH config forms. `baseUrl` is the complete HTTP(S) System One endpoint, `model` names the provider model, `credentialRef` names a DSH credential reference, `timeoutMs` is the per-attempt deadline, and `features` holds per-feature enablement. A new feature is disabled until explicitly enabled. The page saves or replaces a key through `ctx.credentials`; neither Remote status nor records return the key. An empty endpoint is allowed so the page can load before connection setup. Nonempty endpoints reject URL credentials, queries, and fragments at configuration validation.

## Consumer API

Register a feature from its own Cordis plugin and give the returned disposer to its own effect. Supply the exact live Web root `Agent` from the business invocation; `ctx.userQuestions` verifies that identity before asking the human.

```ts
ctx.effect(() => ctx.jev.registerFeature({
  id: 'my-feature',
  name: 'My feature',
  description: 'What this judgment supports',
}))

const outcome = await ctx.jev.judge({
  featureId: 'my-feature',
  agent: invocation.agent,
  signal: invocation.signal,
  link: { sessionId: invocation.agent.session.id, runId: runId },
  refresh: async (signal) => ({
    state: await readCurrentState(signal),
    questions: [
      { id: 'choice', kind: 'choice', prompt: 'Choose one', options: [
        { id: 'a', description: 'Candidate A' },
        { id: 'b', description: 'Candidate B' },
      ] },
      { id: 'risk', kind: 'score', prompt: 'Rate risk', levels: ['low', 'medium', 'high'] },
      { id: 'ready', kind: 'noul', prompt: 'Is this ready?' },
    ],
  }),
  interpret: (response) => businessCanUse(response)
    ? { usable: true }
    : { usable: false, reason: 'The answer does not resolve this operation' },
  canAdopt: () => targetIsCurrent() ? true : 'Target changed during judgment',
})

if (outcome.kind !== 'ok') return
const executed = await performBusinessAction(outcome.response)
await ctx.jev.writeReceipt(outcome.operationId, {
  id: actionId,
  status: executed ? 'executed' : 'execution-failed',
  at: new Date().toISOString(),
})
```

`refresh` runs again only after a human selects Retry. A retry reads the latest connection, credential, feature switch, and business input. If the feature was disabled while waiting, the service asks the human to enable it or cancel and sends no new request. Disabling an already sent judgment does not cancel that attempt. Choice preserves the selected option and service probability distribution. Score preserves the fractional position in the ordered rubric (`1.5` is valid for three levels), without normalization. Noul preserves its probability of true separately from optional confidence. A missing, malformed, or out-of-range answer cannot return `kind: 'ok'`.

Before every HTTP call, the service durably writes the exact JSON state and questions. It uses `ctx.llm.stream` with a versioned JSON envelope containing that same snapshot; the dedicated adapter sends the System One HTTP body and rejects ordinary chat calls. A valid result must be durably written before it is returned. Transport, timeout, validation, and business-interpretation failures wait for an explicit human Retry or Cancel; a missing answerer fails the operation. External cancellation stops the dependent operation without cancelling the whole Host Session. Business actions still use the Host's normal tools, guards, and sandbox; `ctx.jev` never performs them.

Each profile stores its own operation and attempt records in a storage domain derived from `ctx.profileContext.dir`. The browser Remote reads only that domain; `listRecords` caps a page at 100 summaries and `getRecord` loads detail on demand. Action receipts are idempotent by receipt id. A conflicting receipt fails, and an absent receipt after a restart means the action result is unconfirmed. If the input write fails, no Jev request is sent; if the result write fails, no answer is returned as usable. Receipt write failure means the caller must investigate the action and must not repeat it merely to repair the record.

## Local Web fixture

The files under `tests/fixtures` are not included in the package. Their private `package.json` gives the test command a separate Loader package identity from `@dsh-jev/plugin`, so the Host plugin remains the single active source of its Web Client. They use only a local HTTP server and a test-only DSH slash command; they do not call a paid service or run the main chat model.

1. Run `node packages/jev/tests/fixtures/system-one-server.mjs` from this workspace. It prints local `/success`, `/invalid-once`, and `/always-invalid` System One URLs. `POST http://127.0.0.1:<printed-port>/reset` resets the one-time failure counter.
2. Start an isolated Web profile with an extra overlay containing `insert: [{ id: jev-fixture, name: /absolute/path/to/packages/jev/tests/fixtures/command.mjs }]`. The ordinary Jev package bundle must already be installed in that profile. The overlay is test-only and is never part of `cordis.patch.yml`.
3. In Jev settings, set a printed local endpoint and a dummy test credential, then enable the registered `fixture` feature. In a real Web root Session, submit `/jev_fixture` in the chat composer. This is a `ctx.commands` human command and supplies its actual `CommandInvocation.agent` to `ctx.jev.judge`; the main model is not invoked. `/invalid-once` shows the human Retry/Cancel flow, and each retry increments the fixture state's `version`. `/jev_fixture stale` records a target that was not adopted. `/jev_fixture undetermined` exercises the consumer's unusable-answer path.

These fixtures establish only local protocol and Web integration. They do not establish compatibility with a paid Jev endpoint or a future DSH release.
