/** Frame-wide feedback for completed Jev settings writes. */

import React from 'react'
import { Toast } from '@deepseek-ai/dsh-client-ui-primitives'
import type { SnapshotStore } from '@deepseek-ai/dsh-client-store'
import type { InjectFace, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type {} from '@deepseek-ai/dsh-client-ui-layout/client'

/** One transient success message retained outside the plugin detail page. */
export interface JevToastMessage { sequence: number; text: string }

/** Store and dismissal injected by the Jev browser registration. */
export interface JevToastFace {
  hooks: { jevToast: SnapshotStore<JevToastMessage | null> }
  dismiss: () => void
}

/** Render the current message in the Host overlay. */
export function JevToast({ useJevToast, dismiss }: PropsRuntime<'shell.overlay'> & InjectFace<JevToastFace>) {
  const message = useJevToast(value => value)
  if (message === null) return null
  return <Toast key={message.sequence} text={message.text} tone="success" onDone={dismiss} />
}
