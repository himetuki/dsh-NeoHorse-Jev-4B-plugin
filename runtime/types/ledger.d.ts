import { type Domain } from '@deepseek-ai/dsh-storage-domain';
import type { JevActionReceipt, JevAttemptRecord, JevOperationLink, JevRecordDetail, JevRecordFilter, JevRecordPage, JevRecordStatus, JevRequest } from './types.ts';
/** Profile directory identity is part of the domain name even when a backend is shared. */
export declare function ledgerSpec(profileDir: string): {
    name: string;
    version: number;
    layout: "per-record";
    tables: {
        operations: import("@deepseek-ai/dsh-storage-domain").DomainTableSpec<string, JevRecordDetail>;
    };
};
/** Every mutator awaits the domain's durable write before returning a record to a caller. */
export declare class JevLedger {
    private readonly domain;
    private constructor();
    static open(facility: {
        open: (spec: ReturnType<typeof ledgerSpec>) => Promise<Domain<ReturnType<typeof ledgerSpec>>>;
    }, profileDir: string): Promise<JevLedger>;
    close(): Promise<void>;
    /** Mark calls and waits left by an earlier Host process as interrupted. */
    private markInterrupted;
    create(featureId: string, link: JevOperationLink, diagnostic?: boolean): Promise<JevRecordDetail>;
    /** Write one stable zero-attempt recovery record in a single durable operation. */
    createInterrupted(featureId: string, link: JevOperationLink): Promise<JevRecordDetail>;
    get(id: string): JevRecordDetail | null;
    startAttempt(operationId: string, request: JevRequest, connection: JevAttemptRecord['connection']): Promise<JevAttemptRecord>;
    settleAttempt(operationId: string, attemptId: string, patch: Pick<JevAttemptRecord, 'status' | 'response' | 'rawResponse' | 'failure' | 'usage' | 'interpretation'>): Promise<void>;
    setStatus(operationId: string, status: JevRecordStatus): Promise<void>;
    /** Preserve a pre-attempt or ledger-stage failure without inventing an HTTP attempt. */
    failOperation(operationId: string, failure: {
        code: string;
        message: string;
    }): Promise<void>;
    receipt(operationId: string, receipt: JevActionReceipt): Promise<JevRecordDetail>;
    list(filter: JevRecordFilter): JevRecordPage;
}
//# sourceMappingURL=ledger.d.ts.map