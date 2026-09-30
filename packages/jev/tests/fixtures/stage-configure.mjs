/** Configure only the isolated Web profile for a localhost stage fixture. */
import { readFile, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../../..')
const home = join(root, '.artifacts/stage-validation/home')
if (resolve(process.env.DSH_HOME ?? '') !== home) {
  throw new Error(`Set DSH_HOME=${home}; refusing another profile home`)
}
const endpoint = new URL(process.argv[2] ?? '')
if (endpoint.protocol !== 'http:' || endpoint.hostname !== '127.0.0.1'
  || !endpoint.pathname.startsWith('/v1/systemone/stage-')
  || endpoint.username || endpoint.password || endpoint.search || endpoint.hash) {
  throw new Error('Fixture endpoint must be a plain 127.0.0.1 System One stage URL')
}
const profilePatch = join(home, 'profiles/stage-validation/cordis.patch.yml')
const existing = await readFile(profilePatch, 'utf8')
const significant = existing.split('\n').map(line => line.trim()).filter(line => line && !line.startsWith('#')).join('\n')
if (significant !== '[]' && !existing.includes('# Generated stage-validation fixture profile')) {
  throw new Error('Refusing to overwrite a non-fixture profile patch')
}
const credentialPath = join(home, '.credentials.yaml')
let credentialExists = false
try {
  const credential = await readFile(credentialPath, 'utf8')
  credentialExists = true
  if (!credential.includes('STAGE_FIXTURE_KEY: localhost-only-test-value')) {
    throw new Error('Refusing to overwrite a non-fixture credentials document')
  }
} catch (error) {
  if (error?.code !== 'ENOENT') throw error
}
if (!credentialExists) {
  await writeFile(credentialPath, 'version: 1\nrefs:\n  STAGE_FIXTURE_KEY: localhost-only-test-value\n',
    { flag: 'wx', mode: 0o600 })
}
await writeFile(profilePatch, `# Generated stage-validation fixture profile; no paid model endpoint is configured.\n- id: jev\n  config:\n    baseUrl: ${endpoint.href}\n    model: stage-fixture-system-one\n    credentialRef: STAGE_FIXTURE_KEY\n    timeoutMs: 10000\n    features:\n      stage-navigation: false\n`)
process.stdout.write(JSON.stringify({ profile: profilePatch, endpoint: endpoint.href,
  featureInitiallyEnabled: false, dummyCredential: true }) + '\n')
