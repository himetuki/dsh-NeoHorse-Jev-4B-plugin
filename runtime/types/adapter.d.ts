import { LlmAdapter, type GenerateOptions, type StreamChunk } from '@deepseek-ai/dsh-llm';
import type { JevRequest } from './types.ts';
export declare const JEV_PROVIDER = "jev-system-one";
export interface JevConnection {
    baseUrl: string;
    model: string;
    credentialRef: string;
    apiKey: string;
    timeoutMs: number;
}
/** The adapter never advertises a chat model and rejects calls lacking a service-issued nonce. */
export declare class JevAdapter extends LlmAdapter {
    private readonly pending;
    issue(request: JevRequest, connection: JevConnection, canStart?: () => boolean): {
        envelope: string;
        release: () => void;
    };
    stream(options: GenerateOptions): AsyncIterable<StreamChunk>;
    private envelope;
}
//# sourceMappingURL=adapter.d.ts.map