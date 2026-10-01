/** Check the declared DSH file policy before any model request. */
import { spawnSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { writeFileSync } from 'node:fs'

const requireFromDsh = createRequire(process.env.JEV_EVAL_DSH_PACKAGE_JSON)
const { Context } = await import(requireFromDsh.resolve('@deepseek-ai/cordis'))
const { LocalSandboxProvider } = await import(requireFromDsh.resolve('@deepseek-ai/dsh-sandbox-local'))

const workspaceRoot = process.env.JEV_EVAL_SANDBOX_WORKDIR
const markerPath = process.env.JEV_EVAL_SANDBOX_PRECHECK_MARKER
const mode = process.env.JEV_EVAL_SANDBOX_MODE
if (!workspaceRoot?.startsWith('/') || !markerPath?.startsWith('/')) {
  throw new Error('Sandbox precheck requires absolute workdir and marker paths')
}
if (mode !== 'workspace-write' && mode !== 'danger-full-access') {
  throw new Error('Sandbox precheck requires a supported DSH file policy')
}

const marker = { mode, status: 'failed', enforcement: null,
  runner: null, exit_code: null, error_code: null, diagnostic: null }
let fiber
try {
  if (mode === 'danger-full-access') {
    // DSH's bash consumer runs the original argv directly in this mode.
    marker.enforcement = 'none'
    const run = spawnSync('/usr/bin/true', [], {
      cwd: workspaceRoot, timeout: 5000, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'],
    })
    marker.exit_code = run.status
    if (run.status === 0) marker.status = 'ready'
    else {
      marker.error_code = 'DIRECT_EXECUTION_FAILED'
      marker.diagnostic = (run.error?.message ?? run.stderr ?? '').trim().slice(0, 500)
    }
  } else {
    const ctx = new Context()
    fiber = ctx.plugin(LocalSandboxProvider, {})
    await fiber
    const confined = await ctx.sandbox.confine(['/usr/bin/true'], {
      mode: 'workspace-write', workspaceRoot,
    })
    marker.enforcement = confined.enforcement
    marker.runner = confined.argv[0]
    if (confined.enforcement !== 'full') {
      marker.error_code = 'PARTIAL_ENFORCEMENT'
    } else {
      const run = spawnSync(confined.argv[0], confined.argv.slice(1), {
        cwd: workspaceRoot, timeout: 5000, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'],
      })
      marker.exit_code = run.status
      if (run.status === 0) marker.status = 'ready'
      else {
        marker.error_code = 'RUNNER_EXECUTION_FAILED'
        marker.diagnostic = (run.error?.message ?? run.stderr ?? '').trim().slice(0, 500)
      }
    }
  }
} catch (error) {
  marker.error_code = typeof error?.code === 'string' ? error.code : 'PROBE_FAILED'
  marker.diagnostic = String(error?.message ?? error).slice(0, 500)
} finally {
  if (fiber) await fiber.dispose()
  writeFileSync(markerPath, JSON.stringify(marker) + '\n', { mode: 0o600 })
}
if (marker.status !== 'ready') {
  console.error(`DSH ${mode} file policy precheck failed: ${marker.error_code}`)
  process.exitCode = 2
}
