/** Optional, recoverable admission of model-visible command and test logs. */
import type { Context, Volatile } from '@deepseek-ai/cordis';
import s from '@deepseek-ai/schemastery';
import type { OutputAdmissionConfigValues } from './output-admission-types.ts';
/** Live profile limits. Feature switches belong to the shared Jev service. */
export interface Config {
    [key: string]: Volatile<number>;
}
export declare const Config: s<OutputAdmissionConfigValues, Config>;
/** Install two independently disabled admission branches on top-level tool results. */
export declare function apply(ctx: Context, config: Config): void;
export declare const inject: string[];
export declare const name = "jev-output-admission";
//# sourceMappingURL=output-admission.d.ts.map