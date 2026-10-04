import { LlmAdapter, type GenerateOptions, type StreamChunk } from '@deepseek-ai/dsh-llm';
import type { JevRequest } from './types.ts';
export declare const JEV_PROVIDER = "jev-system-one";
export interface JevConnection {
    baseUrl: string;
    model: string;
    credentialRef: string;
    apiKey: string;
    timeoutMs: number;
    /** Estimated input tokens one call may carry; absent means the built-in default. */
    maxInputTokens?: number;
}
/** The adapter never advertises a chat model and rejects calls lacking a service-issued nonce. */
export declare class JevAdapter extends LlmAdapter {
    private readonly pending;
    issue(request: JevRequest, connection: JevConnection, canStart?: () => boolean): {
        envelope: string;
        release: () => void;
    };
    stream(options: GenerateOptions): AsyncIterable<StreamChunk>;
    /**
     * Send one request per ≤16-question batch and merge every batch answer into a
     * single System One response body. Local input is never truncated: an
     * oversized body fails before dispatch, and a partial batch set fails as a whole.
     */
    private dispatch;
    /** One non-streaming JSON POST with the provider's error envelope preserved. */
    private post;
    /** Map one provider status to a stable code and keep its code/message/traceId for troubleshooting. */
    private failure;
    private envelope;
}
//# sourceMappingURL=adapter.d.ts.map