/** Supply one isolated Pier batch from DSH's normal credential service. */
import { spawn } from 'node:child_process'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createInterface } from 'node:readline'
import { fileURLToPath } from 'node:url'
import { Context } from '@deepseek-ai/cordis'
import { loadLayeredEnv } from '@deepseek-ai/dsh-app-boot'
import { credentialRef } from '@deepseek-ai/dsh-credentials'
import { LocalCredentialProvider } from '@deepseek-ai/dsh-credentials-local'

const ROOT = fileURLToPath(new URL('../..', import.meta.url))
const SENSITIVE_NAME = /(KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL|AUTH)/i

function option(args, name) {
  const index = args.indexOf(name)
  if (index < 0 || index + 1 >= args.length) throw new Error(`Missing ${name}`)
  return args[index + 1]
}

async function jevKeyFromStdin() {
  const lines = createInterface({ input: process.stdin, terminal: false })
  try {
    for await (const line of lines) {
      const key = line.trim()
      if (!key || key.length > 4096) throw new Error('Invalid Jev key input')
      return key
    }
    throw new Error('Missing Jev key input')
  } finally {
    lines.close()
  }
}

async function main(args) {
  const stdinKey = args.includes('--jev-key-stdin')
  args = args.filter(value => value !== '--jev-key-stdin')
  const action = args[0]
  if (!['run', 'resume'].includes(action) || !args.includes('--execute')) {
    throw new Error('Use run or resume with --execute; use the Python CLI for non-executing checks')
  }
  const manifest = action === 'run'
    ? option(args, '--manifest')
    : resolve(option(args, '--batch'), 'manifest.json')
  const plan = JSON.parse(await readFile(resolve(manifest), 'utf8'))
  const names = [plan?.conditions?.main_credential_env, plan?.jev?.credential_env]
  if (plan?.phase === 'smoke' || names.some(name => typeof name !== 'string' ||
      !/^[A-Za-z_][A-Za-z0-9_]*$/.test(name))) {
    throw new Error('A real batch must declare two valid credential references')
  }
  if (stdinKey && plan.jev.credential_env !== 'JEV_API_KEY') {
    throw new Error('Jev stdin input requires the JEV_API_KEY reference')
  }

  // This is the same launch-environment snapshot and credential provider used
  // by DSH. Neither user profiles nor Session data are loaded here.
  const ctx = new Context()
  ctx.provide('launchEnvironment', loadLayeredEnv('jev-deepswe', ROOT))
  const fiber = ctx.plugin(LocalCredentialProvider, { watch: false })
  try {
    await fiber
    const childEnv = Object.fromEntries(Object.entries(process.env)
      .filter(([name]) => !SENSITIVE_NAME.test(name) && name !== 'DSH_HOME'))
    for (const name of new Set(names)) {
      if (stdinKey && name === 'JEV_API_KEY') continue
      const ref = credentialRef(name)
      const availability = await ctx.credentials.describe(ref)
      if (!availability.configured) throw new Error(`DSH credential reference ${name} is not configured`)
      const credential = await ctx.credentials.resolve(ref)
      if (!credential?.value) throw new Error(`DSH credential reference ${name} is unavailable`)
      childEnv[name] = credential.value
    }
    if (stdinKey) childEnv.JEV_API_KEY = await jevKeyFromStdin()
    const child = spawn('python3', ['-m', 'bench.deepswe.cli', ...args], {
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
  // Native credential diagnostics can mention paths and names, but this
  // launcher never renders an error object or a resolved secret.
  console.error(error instanceof Error && /^DSH credential reference [A-Za-z_][A-Za-z0-9_]* (?:is not configured|is unavailable)$/.test(error.message)
    ? error.message : 'DeepSWE credential launch failed before starting Pier')
  process.exitCode = 2
}
