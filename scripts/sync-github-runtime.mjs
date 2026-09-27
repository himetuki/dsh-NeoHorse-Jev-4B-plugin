/** Copy built plugin files into the runtime shipped by GitHub installs. */
import { copyFile, mkdir, readdir, readFile, rm, writeFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'

const source = resolve('packages/jev/lib')
const target = resolve('runtime')
const files = []
async function collect(directory, prefix = '') {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const relative = join(prefix, entry.name)
    if (entry.isDirectory()) await collect(join(directory, entry.name), relative)
    else if (entry.isFile() && (entry.name.endsWith('.js') || entry.name.endsWith('.d.ts'))) files.push(relative)
  }
}
await collect(source)
if (!files.includes('index.js') || !files.includes('client.js')) throw new Error('Build the plugin before synchronizing runtime')
await rm(target, { recursive: true, force: true })
for (const relative of files) {
  const destination = join(target, relative)
  await mkdir(resolve(destination, '..'), { recursive: true })
  const text = await readFile(join(source, relative), 'utf8')
  const portable = text.replace(/^[\t ]*\/\/#region[^\n]*jev-css:[^\n]*[/\\]([^/\\\r\n]+)\.mjs\r?$/gm, '//#region jev-css:$1')
  await writeFile(destination, portable)
}
await copyFile('packages/jev/THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_NOTICES.md')
