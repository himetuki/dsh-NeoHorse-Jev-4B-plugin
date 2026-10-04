/** Dedicated System One adapter used only by JevService's typed one-shot calls. */
import { randomUUID } from 'node:crypto';
import { LlmAdapter, LlmError, attributionHeaders } from '@deepseek-ai/dsh-llm';
import { DEFAULT_MAX_INPUT_TOKENS, MAX_CHOICE_OPTIONS_PER_QUESTION, oversizedQuestion, requestTokens } from "./budget.js";
import { validateRequest, wireBody } from "./wire.js";
export const JEV_PROVIDER = 'jev-system-one';
/**
 * NeoHorse-Jev-4B accepts at most 16 plain-text questions per call and rejects
 * a larger batch. A judgment that needs more questions is split into ordered
 * batches whose answers are merged back into one response, so consumers keep
 * one typed judgment per operation.
 */
const MAX_QUESTIONS_PER_CALL = 16;
/** Provider ceiling for one plain-text request body: 1 MiB. */
const MAX_REQUEST_BYTES = 1_048_576;
/** Provider-independent ceiling on one response body, retained from the single-call guard. */
const MAX_RESPONSE_CHARS = 2_000_000;
/** Bounded provider error facts retained beside a failure for troubleshooting. */
const MAX_ERROR_DETAIL_CHARS = 400;
/** Bounded bytes read from a failing response body. */
const MAX_ERROR_BODY_CHARS = 4_096;
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
        const merged = await this.dispatch(connection, request, options.signal);
        const text = JSON.stringify(merged);
        yield { type: 'block-start', index: 0, blockType: 'text' };
        yield { type: 'text-delta', index: 0, text };
        yield { type: 'block-end', index: 0, block: { type: 'text', text } };
        yield { type: 'finish', reason: { kind: 'stop' } };
    }
    /**
     * Send one request per ≤16-question batch and merge every batch answer into a
     * single System One response body. Local input is never truncated: an
     * oversized body fails before dispatch, and a partial batch set fails as a whole.
     */
    async dispatch(connection, request, signal) {
        const batches = [];
        for (let index = 0; index < request.questions.length; index += MAX_QUESTIONS_PER_CALL) {
            batches.push(request.questions.slice(index, index + MAX_QUESTIONS_PER_CALL));
        }
        // The provider rejects an over-budget call with 422, which is indistinguishable from a protocol
        // error and leaves the feature permanently skipped. Every batch carries the same state, so the
        // budget is checked per batch here and the call fails locally with a reason the ledger explains.
        const budget = connection.maxInputTokens ?? DEFAULT_MAX_INPUT_TOKENS;
        for (const questions of batches) {
            const oversized = oversizedQuestion(questions);
            if (oversized !== undefined) {
                throw new LlmError(`Jev choice ${oversized.id} carries ${String(oversized.options.length)} options, above the local cap of ${String(MAX_CHOICE_OPTIONS_PER_QUESTION)}`, 'INPUT_TOO_LARGE');
            }
            const estimated = requestTokens({ state: request.state, questions });
            if (estimated > budget) {
                throw new LlmError(`Jev request is about ${String(Math.round(estimated))} input tokens, above the configured ${String(budget)}; reduce the feature's character budget or raise maxInputTokens`, 'INPUT_TOO_LARGE');
            }
        }
        const answers = {};
        let model;
        let extensions;
        let usageComplete = true;
        let inputTokens = 0;
        let outputTokens = 0;
        for (const [index, questions] of batches.entries()) {
            if (signal?.aborted)
                throw new LlmError('Jev request was cancelled or timed out', 'ABORTED');
            const payload = JSON.stringify(wireBody(connection.model, { state: request.state, questions }));
            const bytes = new TextEncoder().encode(payload).length;
            if (bytes > MAX_REQUEST_BYTES) {
                throw new LlmError(`Jev request body is ${String(bytes)} bytes, above the provider's 1 MiB limit; reduce the judgment input`, 'BAD_REQUEST');
            }
            const answered = await this.post(connection, payload, signal);
            const batchAnswers = answered.answers;
            if (typeof batchAnswers !== 'object' || batchAnswers === null || Array.isArray(batchAnswers)) {
                throw new LlmError('Jev response has no answers object', 'INVALID_RESPONSE');
            }
            for (const [id, value] of Object.entries(batchAnswers))
                answers[id] = value;
            if (index === 0) {
                if (answered.model !== undefined)
                    model = answered.model;
                if (answered.extensions !== undefined)
                    extensions = answered.extensions;
            }
            const batchUsage = readUsage(answered.usage);
            if (batchUsage === undefined)
                usageComplete = false;
            else {
                inputTokens += batchUsage.inputTokens;
                outputTokens += batchUsage.outputTokens;
            }
        }
        return {
            ...model === undefined ? {} : { model },
            answers,
            ...usageComplete && batches.length > 0 ? { usage: { input_tokens: inputTokens, output_tokens: outputTokens } } : {},
            ...extensions === undefined ? {} : { extensions },
        };
    }
    /** One non-streaming JSON POST with the provider's error envelope preserved. */
    async post(connection, payload, signal) {
        const response = await fetch(connection.baseUrl, {
            method: 'POST',
            headers: {
                ...attributionHeaders(),
                authorization: `Bearer ${connection.apiKey}`,
                'content-type': 'application/json',
                accept: 'application/json',
            },
            body: payload,
            signal,
        }).catch(error => {
            if (signal?.aborted)
                throw new LlmError('Jev request was cancelled or timed out', 'ABORTED');
            throw new LlmError('Jev service could not be reached', 'NETWORK', { cause: error });
        });
        if (!response.ok)
            throw await this.failure(response);
        const raw = await response.text();
        if (raw.length > MAX_RESPONSE_CHARS)
            throw new LlmError('Jev response exceeds 2 MB', 'INVALID_RESPONSE');
        let json;
        try {
            json = JSON.parse(raw);
        }
        catch {
            throw new LlmError('Jev response is not JSON', 'INVALID_RESPONSE');
        }
        if (typeof json !== 'object' || json === null || Array.isArray(json)) {
            throw new LlmError('Jev response is not a JSON object', 'INVALID_RESPONSE');
        }
        return json;
    }
    /** Map one provider status to a stable code and keep its code/message/traceId for troubleshooting. */
    async failure(response) {
        const code = response.status === 401 || response.status === 403 ? 'AUTH'
            : response.status === 402 ? 'PAYMENT_REQUIRED'
                : response.status === 429 ? 'RATE_LIMIT'
                    : response.status >= 500 ? 'SERVER' : 'BAD_REQUEST';
        const detail = await providerDetail(response);
        return new LlmError(`Jev service returned HTTP ${String(response.status)}${detail === undefined ? '' : ` (${detail})`}`, code, { status: response.status });
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
/** Read the provider's optional `usage` counts; an unusable shape is reported as unknown rather than guessed. */
function readUsage(value) {
    if (typeof value !== 'object' || value === null || Array.isArray(value))
        return undefined;
    const input = value.input_tokens;
    const output = value.output_tokens;
    if (!Number.isSafeInteger(input) || !Number.isSafeInteger(output) || input < 0 || output < 0)
        return undefined;
    return { inputTokens: input, outputTokens: output };
}
/** Bounded provider error facts (`code`, `message`, `traceId`) with credential-shaped text removed. */
async function providerDetail(response) {
    let text;
    try {
        text = (await response.text()).slice(0, MAX_ERROR_BODY_CHARS);
    }
    catch {
        return undefined;
    }
    const parts = [];
    try {
        const parsed = JSON.parse(text);
        if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
            const envelope = parsed;
            for (const key of ['code', 'message', 'traceId']) {
                const value = envelope[key];
                if (typeof value === 'string' && value.trim() !== '')
                    parts.push(`${key}=${redact(value.trim())}`);
            }
        }
    }
    catch { /* a non-JSON error body is summarized as text below */ }
    if (parts.length === 0) {
        const summary = redact(text.replaceAll(/\s+/gu, ' ').trim());
        if (summary !== '')
            parts.push(`body=${summary}`);
    }
    if (parts.length === 0)
        return undefined;
    const detail = parts.join('; ');
    return detail.length > MAX_ERROR_DETAIL_CHARS ? `${detail.slice(0, MAX_ERROR_DETAIL_CHARS)}…` : detail;
}
/** Remove credential-shaped text before provider words reach a profile record. */
function redact(text) {
    return text
        .replaceAll(/sk[-_][A-Za-z0-9_-]{6,}/gu, '[redacted-key]')
        .replaceAll(/Bearer\s+[A-Za-z0-9._~+/=-]{8,}/gu, 'Bearer [redacted]');
}
//# sourceMappingURL=adapter.js.map