/** Dedicated System One adapter used only by JevService's typed one-shot calls. */
import { randomUUID } from 'node:crypto';
import { LlmAdapter, LlmError, attributionHeaders } from '@deepseek-ai/dsh-llm';
import { validateRequest, wireBody } from "./wire.js";
export const JEV_PROVIDER = 'jev-system-one';
/** The adapter never advertises a chat model and rejects calls lacking a service-issued nonce. */
export class JevAdapter extends LlmAdapter {
    pending = new Map();
    issue(request, connection, canStart) {
        const nonce = randomUUID();
        this.pending.set(nonce, { request, connection, canStart });
        return {
            envelope: JSON.stringify({ version: 1, nonce, state: request.state, questions: request.questions }),
            release: () => { this.pending.delete(nonce); },
        };
    }
    async *stream(options) {
        const { nonce, request } = this.envelope(options);
        const call = this.pending.get(nonce);
        if (call === undefined || options.model !== call.connection.model
            || JSON.stringify(request) !== JSON.stringify(call.request)) {
            throw new LlmError('Jev accepts only issued typed judgments', 'UNSUPPORTED_OPTION');
        }
        const { connection } = call;
        if (call.canStart?.() === false)
            throw new LlmError('Jev feature was disabled before dispatch', 'FEATURE_DISABLED');
        const response = await fetch(connection.baseUrl, {
            method: 'POST',
            headers: {
                ...attributionHeaders(),
                authorization: `Bearer ${connection.apiKey}`,
                'content-type': 'application/json',
                accept: 'application/json',
            },
            body: JSON.stringify(wireBody(connection.model, request)),
            signal: options.signal,
        }).catch(error => {
            if (options.signal?.aborted)
                throw new LlmError('Jev request was cancelled or timed out', 'ABORTED');
            throw new LlmError('Jev service could not be reached', 'NETWORK', { cause: error });
        });
        if (!response.ok) {
            const code = response.status === 401 || response.status === 403 ? 'AUTH'
                : response.status === 402 ? 'PAYMENT_REQUIRED'
                    : response.status === 429 ? 'RATE_LIMIT'
                        : response.status >= 500 ? 'SERVER' : 'BAD_REQUEST';
            throw new LlmError(`Jev service returned HTTP ${response.status}`, code, { status: response.status });
        }
        const raw = await response.text();
        if (raw.length > 2_000_000)
            throw new LlmError('Jev response exceeds 2 MB', 'INVALID_RESPONSE');
        let json;
        try {
            json = JSON.parse(raw);
        }
        catch {
            throw new LlmError('Jev response is not JSON', 'INVALID_RESPONSE');
        }
        const text = JSON.stringify(json);
        yield { type: 'block-start', index: 0, blockType: 'text' };
        yield { type: 'text-delta', index: 0, text };
        yield { type: 'block-end', index: 0, block: { type: 'text', text } };
        yield { type: 'finish', reason: { kind: 'stop' } };
    }
    envelope(options) {
        if (options.provider !== JEV_PROVIDER || options.system !== undefined || options.tools !== undefined
            || options.temperature !== undefined || options.stop !== undefined || options.maxTokens !== undefined
            || options.reasoningEffort !== undefined || options.messages.length !== 1) {
            throw new LlmError('Jev is not a chat model', 'UNSUPPORTED_OPTION');
        }
        const message = options.messages[0];
        const content = message?.role === 'user' ? message.content : undefined;
        if (!Array.isArray(content) || content.length !== 1 || content[0]?.type !== 'text') {
            throw new LlmError('Jev accepts only issued typed judgments', 'UNSUPPORTED_OPTION');
        }
        let raw;
        try {
            raw = JSON.parse(content[0].text);
        }
        catch {
            throw new LlmError('Jev typed request envelope is invalid', 'UNSUPPORTED_OPTION');
        }
        if (typeof raw !== 'object' || raw === null || Array.isArray(raw)
            || !('version' in raw) || raw.version !== 1
            || !('nonce' in raw) || typeof raw.nonce !== 'string'
            || !('state' in raw) || !('questions' in raw)) {
            throw new LlmError('Jev typed request envelope is invalid', 'UNSUPPORTED_OPTION');
        }
        const request = { state: raw.state, questions: raw.questions };
        try {
            validateRequest(request);
        }
        catch {
            throw new LlmError('Jev typed request envelope is invalid', 'UNSUPPORTED_OPTION');
        }
        return { nonce: raw.nonce, request };
    }
}
//# sourceMappingURL=adapter.js.map