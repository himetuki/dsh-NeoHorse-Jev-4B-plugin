import type { Context, Volatile } from '@deepseek-ai/cordis';
import s from '@deepseek-ai/schemastery';
export declare const name = "jev-shared-findings";
export declare const inject: string[];
export interface Config {
    maxRequestChars: Volatile<number>;
}
/** Maximum serialized judgment input; oversized originals remain stored and require manual resolution. */
export declare const Config: s<{
    maxRequestChars: number;
}, Config>;
declare module '@deepseek-ai/dsh-llm' {
    interface MessageSourceMap {
        'jev-shared-findings': {
            kind: 'jev-shared-findings';
            form: 'notice';
            summary: string;
            relationId: string;
        };
    }
}
/** Install the shared-source observer and the corresponding step-admission wait. */
export declare function apply(ctx: Context, config: Config): Promise<void>;
//# sourceMappingURL=shared-findings.d.ts.map