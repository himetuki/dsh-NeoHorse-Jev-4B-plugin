/** Browser lifecycle for the Jev Remote contribution and plugin-owned pages. */
import type { Context } from '@deepseek-ai/cordis';
import type { TypertRemoteContribution } from '@deepseek-ai/dsh-typert-protocol';
import { type JevLocaleKey } from './locales.ts';
declare module '@deepseek-ai/dsh-client-ui-slots' {
    interface LocaleNamespaceMap {
        /** Jev settings and record-browser copy. */
        'jev.plugin': JevLocaleKey;
    }
}
/** Services needed after the generated Jev Remote contribution mounts. */
export declare const inject: string[];
/**
 * Mount Jev's generated Remote first, then register the bundle page while its settings entry is served.
 * @param ctx - Client runtime with Remote, locale, slots, and config forms.
 * @param contribution - generated Jev Remote namespace.
 * @returns disposer for both Remote and UI registrations.
 */
export declare function mountJevUi(ctx: Context, contribution: TypertRemoteContribution): Promise<() => Promise<void>>;
//# sourceMappingURL=mount.d.ts.map