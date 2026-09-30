/** Tie the Session tab lifetime to the independent Jev feature switch. */

import type { ConfigForm } from '@deepseek-ai/dsh-client-ui-settings/client'
import type { JevConfigValues } from './JevPage.tsx'

/**
 * Register the stage view only while the feature is explicitly enabled.
 * @param form - Host-owned Jev settings snapshot.
 * @param register - contributes the conversation view and returns its disposer.
 * @returns unsubscribes and removes any active view.
 */
export function watchStageView(
  form: Pick<ConfigForm<JevConfigValues>, 'getSnapshot' | 'subscribe'>,
  register: () => () => void,
): () => void {
  let disposeView: (() => void) | undefined
  const sync = () => {
    const enabled = form.getSnapshot().value?.features['stage-navigation'] === true
    if (enabled && disposeView === undefined) disposeView = register()
    else if (!enabled && disposeView !== undefined) {
      disposeView()
      disposeView = undefined
    }
  }
  const unsubscribe = form.subscribe(sync)
  sync()
  return () => { unsubscribe(); disposeView?.(); disposeView = undefined }
}
