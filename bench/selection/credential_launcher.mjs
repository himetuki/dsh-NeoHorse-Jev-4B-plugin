/** Supply one selection trial from DSH's normal local credential service. */
import { spawn } from 'node:child_process'
import { readFile } from 'node:fs/promises'
import { delimiter, resolve } from 'node:path'
import { createInterface } from 'node:readline'
import { fileURLToPath } from 'node:url'
import { Context } from '@deepseek-ai/cordis'
import { loadLayeredEnv } from '@deepseek-ai/dsh-app-boot'
import { credentialRef } from '@deepseek-ai/dsh-credentials'
import { LocalCredentialProvider } from '@deepseek-ai/dsh-credentials-local'

const ROOT = fileURLToPath(new URL('../..', import.meta.url))
const SENSITIVE_NAME = /(KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL|AUTH)/i
const CASES = ['zero', 'single', 'twelve', 'nested-sixteen', 'multi-forty', 'over-forty-one']

function option(args, name) {
  const index = args.indexOf(name)
  if (index < 0 || index + 1 >= args.length) throw new Error(`Missing ${name}`)
  return args[index + 1]
}

async function keyFromStdin() {
  if (process.stdin.isTTY) throw new Error('Jev stdin source must not echo input')
  const lines = createInterface({ input: process.stdin, terminal: false })
  try {
    for await (const line of lines) {
      const key = line.trim()
      if (!key || key.length > 4096) throw new Error('Invalid key input')
      return key
    }
    throw new Error('Missing key input')
  } finally {
    lines.close()
  }
}

async function main(args) {
  const stdinKey = args.includes('--jev-key-stdin')
  args = args.filter(value => value !== '--jev-key-stdin')
  if (args[0] !== 'run' || !args.includes('--execute') || !CASES.includes(option(args, '--case'))
      || !['baseline', 'file-ranking'].includes(option(args, '--condition'))) {
    throw new Error('One explicit, fixed selection trial is required')
  }
  const batch = resolve(option(args, '--batch'))
  const plan = JSON.parse(await readFile(resolve(batch, 'manifest.json'), 'utf8'))
  const mainRef = plan?.conditions?.main_credential_env
  const jevRef = plan?.jev?.credential_env
  if (plan?.phase !== 'pilot' || plan?.selection_suite?.schema !== 1
      || [mainRef, jevRef].some(name => typeof name !== 'string' || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(name))) {
    throw new Error('Frozen selection manifest or credential references are invalid')
  }
  if (stdinKey && jevRef !== 'JEV_API_KEY') throw new Error('Jev stdin input requires JEV_API_KEY')

  const ctx = new Context()
  ctx.provide('launchEnvironment', loadLayeredEnv('jev-deepswe', ROOT))
  const fiber = ctx.plugin(LocalCredentialProvider, { watch: false })
  try {
    await fiber
    const childEnv = Object.fromEntries(Object.entries(process.env)
      .filter(([name]) => !SENSITIVE_NAME.test(name) && name !== 'DSH_HOME'))
    for (const name of new Set([mainRef, jevRef])) {
      if (stdinKey && name === 'JEV_API_KEY') continue
      const ref = credentialRef(name)
      const availability = await ctx.credentials.describe(ref)
      if (!availability.configured) throw new Error(`DSH credential reference ${name} is not configured`)
      const value = await ctx.credentials.resolve(ref)
      if (!value?.value) throw new Error(`DSH credential reference ${name} is unavailable`)
      childEnv[name] = value.value
    }
    if (stdinKey) childEnv.JEV_API_KEY = await keyFromStdin()
    childEnv.PYTHONPATH = [ROOT, childEnv.PYTHONPATH ?? ''].join(delimiter)
    const child = spawn('uv', ['run', '--project', plan.paths.pier, 'python', '-m', 'bench.selection.cli', ...args], {
      cwd: ROOT, env: childEnv, stdio: 'inherit',
    })
    return await new Promise((done, fail) => {
      child.once('error', fail)
      child.once('exit', (code, signal) => done(signal ? 128 + (signal === 'SIGINT' ? 2 : 15) : code ?? 1))
    })
  } finally {
    await fiber.dispose()
  }
}

try {
  process.exitCode = await main(process.argv.slice(2))
} catch (error) {
  console.error(error instanceof Error && /^DSH credential reference [A-Za-z_][A-Za-z0-9_]* (?:is not configured|is unavailable)$/.test(error.message)
    ? error.message : 'Selection credential launch failed before or during Pier')
  process.exitCode = 2
}
