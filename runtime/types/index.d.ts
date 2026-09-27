/** Jev common Host service and typed consumer API. */
import { Service, type Context, type Volatile } from '@deepseek-ai/cordis';
import s from '@deepseek-ai/schemastery';
import { TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol';
import type { Agent } from '@deepseek-ai/dsh-agent/types';
import type { JevActionReceipt, JevCredentialStatus, JevFeatureDefinition, JevFeatureView, JevOperationLink, JevProbeResult, JevRecordDetail, JevRecordFilter, JevRecordPage, JevRequest, JevResponse } from './types.ts';
export type * from './types.ts';
export { JEV_PROVIDER } from './adapter.ts';
/** Current-profile configuration. Every field is editable through DSH configForms. */
export interface Config {
    baseUrl: Volatile<string>;
    model: Volatile<string>;
    credentialRef: Volatile<string>;
    timeoutMs: Volatile<number>;
    features: Volatile<Record<string, boolean>>;
}
interface ConfigValues {
    baseUrl: string;
    model: string;
    credentialRef: string;
    timeoutMs: number;
    features: Record<string, boolean>;
}
/** A consumer refreshes this input for every manual attempt. */
export interface JevJudgeOptions {
    featureId: string;
    link: JevOperationLink;
    agent: Agent;
    refresh: (signal: AbortSignal) => JevRequest | Promise<JevRequest>;
    interpret?: (response: JevResponse, signal: AbortSignal) => {
        usable: true;
    } | {
        usable: false;
        reason: string;
    } | Promise<{
        usable: true;
    } | {
        usable: false;
        reason: string;
    }>;
    canAdopt?: (response: JevResponse, signal: AbortSignal) => true | string | Promise<true | string>;
    signal?: AbortSignal;
}
/** A completed judgment is safe to consider only while `kind` is `ok`. */
export type JevJudgeResult = {
    kind: 'ok';
    operationId: string;
    attemptId: string;
    response: JevResponse;
} | {
    kind: 'cancelled';
    operationId: string;
} | {
    kind: 'not-adopted';
    operationId: string;
    reason: string;
};
/** Non-interactive attempts return failure without opening a human question. */
export type JevJudgeOnceResult = JevJudgeResult | {
    kind: 'failed';
    operationId?: string;
    failure: {
        code: string;
        message: string;
    };
};
/** Stable failure code without provider payload or credential text. */
export declare class JevError extends Error {
    readonly code: string;
    constructor(code: string, message: string);
}
declare module '@deepseek-ai/cordis' {
    interface Context {
        jev: JevService;
    }
}
/** Validated live configuration presented through DSH settings. */
export declare const Config: s<ConfigValues, Config>;
/** One profile's public judgment service and browser Remote namespace. */
export declare class JevService extends TypertRemoteService {
    private readonly config;
    static inject: string[];
    static Config: s<ConfigValues, Config>;
    private readonly adapter;
    private readonly features;
    private ledger?;
    private readonly active;
    private readonly controllers;
    private disposing;
    private readonly featureListeners;
    constructor(ctx: Context, config: Config);
    protected [Service.init](): Promise<void>;
    private records;
    /** Register a consumer feature for this Host lifetime; the caller owns the disposer. */
    registerFeature(feature: JevFeatureDefinition): () => void;
    /** Current registrations, with unknown and newly registered ids disabled by default. */
    listFeatures(): Promise<JevFeatureView[]>;
    /** Query only the current profile, with bounded page size and optional filters. */
    listRecords(filter: JevRecordFilter): Promise<JevRecordPage>;
    /** Read one current-profile operation after the list has identified it. */
    getRecord(id: string): Promise<JevRecordDetail | null>;
    /** Report credential presence, source, and writability without its value. */
    getCredentialStatus(): Promise<JevCredentialStatus>;
    /** Save or replace the current profile's configured credential reference. */
    setCredential(value: string): Promise<JevCredentialStatus>;
    /** Run one fixed diagnostic without a business feature or user state. */
    testConnection(signal: AbortSignal): Promise<JevProbeResult>;
    /** Judge one dependent operation; only a human retry invokes `refresh` again. */
    judge(options: JevJudgeOptions): Promise<JevJudgeResult>;
    /** Make one logged attempt without human waiting or automatic retry. Only `ok` permits adoption. */
    judgeOnce(options: JevJudgeOptions): Promise<JevJudgeOnceResult>;
    private runActive;
    private untilAbort;
    private judgeOwned;
    private cancel;
    private isEnabled;
    /** Read this profile's current enablement synchronously; absent feature ids are disabled. */
    isFeatureEnabled(featureId: string): boolean;
    /** Observe committed feature-setting changes synchronously; the consumer owns the disposer. */
    onFeatureStateChange(listener: (features: Readonly<Record<string, boolean>>) => void): () => void;
    private ask;
    private connectionIdentity;
    private tryOnce;
    /** Record interrupted input without a model call, human question, or attempt; stable message links are idempotent. */
    recordInterrupted(featureId: string, link: JevOperationLink): Promise<JevRecordDetail>;
    /** Persist one action receipt; a failed write leaves execution status unconfirmed. */
    writeReceipt(operationId: string, receipt: JevActionReceipt): Promise<JevRecordDetail>;
}
export default JevService;
//# sourceMappingURL=index.d.ts.map