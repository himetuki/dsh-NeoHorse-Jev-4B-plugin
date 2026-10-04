/**
 * Input budget for one System One call.
 *
 * The provider documents a 1 MiB request ceiling, but the decision model behind it has a much
 * smaller effective input budget: measured against this profile's own ledger, requests whose text
 * stayed at or below 12,003 characters were accepted, while 12,015 characters were rejected with
 * `JEV_UPSTREAM_REJECTED` ("upstream rejected the content or input length"). Characters are a poor
 * proxy across scripts -- 12,000 Latin characters are roughly 3,000 tokens, while 12,000 CJK
 * characters are roughly 12,000 -- so the guard estimates tokens instead.
 */
import type { JevQuestion, JevRequest } from './types.ts';
/**
 * Estimated tokens one request may carry.
 *
 * Sized just under the measured acceptance boundary for Latin text (12,000 characters ≈ 3,000
 * tokens) so a request that previously worked still fits, while a script-dense request that the
 * provider would reject is stopped locally instead of returning a 422.
 */
export declare const DEFAULT_MAX_INPUT_TOKENS = 2800;
/** Options one choice question may carry here; the protocol allows 255, but a long option set is a large request. */
export declare const MAX_CHOICE_OPTIONS_PER_QUESTION = 64;
/**
 * Estimate the model tokens a string costs.
 *
 * Deliberately conservative and script-aware: one token per CJK/kana/Hangul code point, one per
 * four other characters. It is an estimate, not a tokenizer -- the point is to catch the order of
 * magnitude difference between a Latin and a CJK request before the provider does.
 */
export declare function estimateTokens(text: string): number;
/** Estimated tokens for the whole request: state, question prompts, option descriptions, criteria. */
export declare function requestTokens(request: JevRequest): number;
/** The first choice question whose option set exceeds the local cap, or undefined. */
export declare function oversizedQuestion(questions: readonly JevQuestion[]): Extract<JevQuestion, {
    kind: 'choice';
}> | undefined;
//# sourceMappingURL=budget.d.ts.map