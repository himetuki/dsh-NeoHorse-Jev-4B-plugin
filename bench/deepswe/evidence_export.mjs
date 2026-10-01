/** Export only Session-linked Jev records and recoverable original tool logs. */
import { createHash } from 'node:crypto'
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, realpathSync, statSync, writeFileSync } from 'node:fs'
import { basename, join, resolve } from 'node:path'

const source = join(process.env.DSH_HOME, 'storages')
const destination = '/logs/agent/dsh-home/storages'
const originals = '/logs/agent/original-logs'
mkdirSync(destination, { recursive: true })
mkdirSync(originals, { recursive: true })
const index = []

for (const domain of existsSync(source) ? readdirSync(source).filter(name => /^jev_[0-9a-f]{20}$/.test(name)) : []) {
  const operations = join(source, domain, 'operations')
  if (!existsSync(operations)) continue
  const output = join(destination, domain, 'operations')
  mkdirSync(output, { recursive: true })
  for (const filename of readdirSync(operations).filter(name => /^[0-9a-f-]+\.json$/.test(name))) {
    const path = join(operations, filename)
    copyFileSync(path, join(output, filename))
    const detail = JSON.parse(readFileSync(path, 'utf8')).record
    if (!['output-admission', 'test-log-admission'].includes(detail?.featureId)) continue
    for (const receipt of detail.receipts ?? []) {
      if (receipt.id !== 'tool-log-final-result') continue
      let locator
      try { locator = JSON.parse(receipt.reason).locator } catch { locator = undefined }
      const row = { operationId: detail.id, callId: detail.link?.inputVersion, locator, status: 'missing' }
      if (typeof locator === 'string' && locator.startsWith('/') && existsSync(locator)) {
        const resolved = realpathSync(locator)
        // A DSH spill reference is an absolute local text artifact. Never copy
        // profiles, credentials, or arbitrary host paths into report evidence.
        if (resolved.startsWith('/tmp/dsh-spill-') && basename(resolved).endsWith('.txt') && statSync(resolved).isFile()) {
          const content = readFileSync(resolved)
          const sha256 = createHash('sha256').update(content).digest('hex')
          const target = join(originals, `${detail.id}-${sha256.slice(0, 12)}.txt`)
          copyFileSync(resolved, target)
          Object.assign(row, { status: 'saved', relativePath: target.replace('/logs/agent/', ''), sha256, bytes: content.length })
        } else row.status = 'unsupported-locator'
      }
      index.push(row)
    }
  }
}
writeFileSync(join(originals, 'index.json'), JSON.stringify(index, null, 2) + '\n')
