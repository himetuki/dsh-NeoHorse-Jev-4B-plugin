/** Profile-owned shared originals, relation decisions, and delivery receipts. */
import { createHash } from 'node:crypto';
import { defineDomain, domainTable } from '@deepseek-ai/dsh-storage-domain';
import { z } from 'zod';
const receiptSchema = z.object({
    agentId: z.string(), messageId: z.string(), state: z.enum(['queued', 'model-received', 'discarded']),
    adopted: z.literal('unknown'),
});
const findingSchema = z.object({
    id: z.string(), rootId: z.string(), senderId: z.string(), original: z.string(),
    source: z.enum(['agent-message', 'subagent-settled', 'tool-report']), toolCallId: z.string().optional(), messageIds: z.array(z.string()),
    recipients: z.array(receiptSchema), supersededBy: z.string().optional(), at: z.string(),
});
const deliverySchema = z.object({
    recipientId: z.string(), state: z.enum(['unconfirmed', 'queued', 'model-received', 'not-delivered']),
    messageId: z.string().optional(), reason: z.string().optional(), adopted: z.literal('unknown'),
});
const relationSchema = z.object({
    id: z.string(), rootId: z.string(), olderId: z.string(), newerId: z.string(),
    state: z.enum(['pending', 'resolved', 'unresolved', 'interrupted']),
    kind: z.enum(['replacement', 'conflict', 'support', 'unrelated', 'unknown']).optional(),
    basis: z.string().optional(), operationId: z.string().optional(),
    deliveries: z.array(deliverySchema), at: z.string(),
});
const backgroundSchema = z.object({ jobId: z.string(), rootId: z.string(), sourceCallId: z.string(), childIds: z.array(z.string()) });
/** Stable source identity deduplicates repeated sharing within one root. */
export function findingId(rootId, senderId, original) {
    return createHash('sha256').update(JSON.stringify([rootId, senderId, original])).digest('hex');
}
/** Business history is separate from the common Jev operation ledger. */
export function sharedFindingsSpec(profileDir) {
    return defineDomain({
        name: 'jev_shared_' + createHash('sha256').update(profileDir).digest('hex').slice(0, 20),
        version: 1, layout: 'per-record',
        tables: { background_sources: domainTable(backgroundSchema), findings: domainTable(findingSchema), relations: domainTable(relationSchema) },
    });
}
/** Durable writes finish before a relation can cause an action. */
export class SharedFindingsStore {
    domain;
    constructor(domain) {
        this.domain = domain;
    }
    static async open(facility, profileDir) {
        const store = new SharedFindingsStore(await facility.open(sharedFindingsSpec(profileDir)));
        for (const relation of store.relations()) {
            if (relation.state === 'pending')
                await store.saveRelation({ ...relation, state: 'interrupted' });
        }
        return store;
    }
    findings() { return [...this.domain.table('findings').entries()].map(([, value]) => value); }
    relations() { return [...this.domain.table('relations').entries()].map(([, value]) => value); }
    finding(id) { return this.domain.table('findings').get(id); }
    relation(id) { return this.domain.table('relations').get(id); }
    async saveFinding(value) { await this.domain.table('findings').put(value.id, value); }
    async saveRelation(value) { await this.domain.table('relations').put(value.id, value); }
    async saveBackgroundSource(value) { await this.domain.table('background_sources').put(findingId(value.rootId, value.jobId, value.sourceCallId), value); }
    async close() { await this.domain.close(); }
}
//# sourceMappingURL=shared-findings-store.js.map