/** Generated Remote envelopes must be unwrapped before the page receives data. */

import { describe, expect, it, vi } from 'vitest'
import { RemoteError, type RemoteResult } from '@deepseek-ai/dsh-typert-protocol'
import { jevPageRemote, type JevWireRemote } from '../src/client/remote-adapter.ts'
import type {
  JevCredentialStatus, JevFeatureView, JevProbeResult, JevRecordDetail, JevRecordPage,
} from '../src/types.ts'

function ok<T>(value: T): RemoteResult<T> { return { ok: true, value } }
function failed<T>(error: RemoteError<'gateway/internal'>): RemoteResult<T> { return { ok: false, error } }

const features: JevFeatureView[] = [{ id: 'example', name: 'Example', description: 'Test', enabled: false }]
const page: JevRecordPage = { items: [], nextCursor: 'next' }
const detail: JevRecordDetail = {
  id: 'record', featureId: 'example', status: 'succeeded', diagnostic: false,
  startedAt: '2026-09-26T00:00:00.000Z', updatedAt: '2026-09-26T00:00:01.000Z',
  attempts: 1, link: {}, attemptRecords: [], receipts: [],
}
const credential: JevCredentialStatus = { configured: true, writable: false, source: 'environment' }
const probe: JevProbeResult = { ok: true, latencyMs: 12, recordId: 'probe' }

function wire(): JevWireRemote {
  return {
    listFeatures: vi.fn(async () => ok(features)),
    listRecords: vi.fn(async () => ok(page)),
    getRecord: vi.fn(async () => ok(detail)),
    testConnection: vi.fn(async () => ok(probe)),
    getCredentialStatus: vi.fn(async () => ok(credential)),
    setCredential: vi.fn(async () => ok(credential)),
  }
}

describe('Jev Remote page adapter', () => {
  it('passes each success value and preserves call arguments', async () => {
    const remote = wire()
    const adapted = jevPageRemote(remote)
    const filter = { featureId: 'example', limit: 25 }
    const signal = new AbortController().signal

    expect(await adapted.listFeatures()).toBe(features)
    expect(await adapted.listRecords(filter)).toBe(page)
    expect(await adapted.getRecord('record')).toBe(detail)
    expect(await adapted.testConnection(signal)).toBe(probe)
    expect(await adapted.getCredentialStatus()).toBe(credential)
    expect(await adapted.setCredential('new-secret')).toBe(credential)
    expect(remote.listRecords).toHaveBeenCalledWith(filter)
    expect(remote.getRecord).toHaveBeenCalledWith('record')
    expect(remote.testConnection).toHaveBeenCalledWith(signal)
    expect(remote.setCredential).toHaveBeenCalledWith('new-secret')
  })

  it('rejects every Remote failure branch before it reaches page data', async () => {
    const error = new RemoteError('gateway/internal', 'Unavailable', {})
    const remote: JevWireRemote = {
      listFeatures: async () => failed<JevFeatureView[]>(error),
      listRecords: async () => failed<JevRecordPage>(error),
      getRecord: async () => failed<JevRecordDetail | null>(error),
      testConnection: async () => failed<JevProbeResult>(error),
      getCredentialStatus: async () => failed<JevCredentialStatus>(error),
      setCredential: async () => failed<JevCredentialStatus>(error),
    }
    const adapted = jevPageRemote(remote)

    await expect(adapted.listFeatures()).rejects.toBe(error)
    await expect(adapted.listRecords({ limit: 25 })).rejects.toBe(error)
    await expect(adapted.getRecord('record')).rejects.toBe(error)
    await expect(adapted.testConnection(new AbortController().signal)).rejects.toBe(error)
    await expect(adapted.getCredentialStatus()).rejects.toBe(error)
    await expect(adapted.setCredential('new-secret')).rejects.toBe(error)
  })
})
