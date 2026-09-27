import type { Context } from '@deepseek-ai/cordis';
import type { Volatile } from '@deepseek-ai/cordis';
import s from '@deepseek-ai/schemastery';
export declare const name = "jev-workspace-approval";
export declare const inject: string[];
/** Profile setting for a complete direct script read. */
export interface Config {
    maxScriptBytes: Volatile<number>;
}
/** Maximum complete direct script read before Jev receives an explicit unavailable fact. */
export declare const Config: s<{
    maxScriptBytes: number;
}, Config>;
/** Register an answerer after native tool dispatch begins, leaving all other approvals to DSH. */
export declare function apply(ctx: Context, config: Config): void;
//# sourceMappingURL=workspace-approval.d.ts.map