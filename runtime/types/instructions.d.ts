import { type Context } from '@deepseek-ai/cordis';
import s from '@deepseek-ai/schemastery';
/** Bounded evidence collection; omitted instructions make the check undetermined. */
export interface Config {
    maxEvidenceChars: number;
    maxSources: number;
    maxOperationChars: number;
}
export declare const Config: s<Config>;
declare module '@deepseek-ai/dsh-llm' {
    interface MessageSourceMap {
        'jev-instruction-guidance': {
            kind: 'jev-instruction-guidance';
            form: 'notice';
            summary: string;
            requestId: string;
            originalIds: string[];
        };
    }
}
/** Observe tool calls without waiting for Jev and deliver only at an already-entering model step. */
export declare function apply(ctx: Context, config: Config): void;
export declare const inject: string[];
export declare const name = "jev-instructions";
//# sourceMappingURL=instructions.d.ts.map