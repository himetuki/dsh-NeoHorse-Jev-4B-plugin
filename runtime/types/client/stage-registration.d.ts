/** Tie the Session tab lifetime to the independent Jev feature switch. */
import type { ConfigForm } from '@deepseek-ai/dsh-client-ui-settings/client';
import type { JevConfigValues } from './JevPage.tsx';
/**
 * Register the stage view only while the feature is explicitly enabled.
 * @param form - Host-owned Jev settings snapshot.
 * @param register - contributes the conversation view and returns its disposer.
 * @returns unsubscribes and removes any active view.
 */
export declare function watchStageView(form: Pick<ConfigForm<JevConfigValues>, 'getSnapshot' | 'subscribe'>, register: () => () => void): () => void;
//# sourceMappingURL=stage-registration.d.ts.map