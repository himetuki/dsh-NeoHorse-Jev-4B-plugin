/** System One request serialization and complete response validation. */
import type { JevRequest, JevResponse, Json } from './types.ts';
/** Reject invalid questions before a ledger write or model call. */
export declare function validateRequest(request: JevRequest): void;
/** Encode the typed public request into the provider's System One HTTP body. */
export declare function wireBody(model: string, request: JevRequest): Json;
/** Parse every answer, including optional probabilities and service signals, or reject the whole request. */
export declare function parseWireResponse(raw: unknown, request: JevRequest): {
    response: JevResponse;
    usage?: {
        inputTokens?: number;
        outputTokens?: number;
    };
    raw: Json;
};
//# sourceMappingURL=wire.d.ts.map