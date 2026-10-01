/** Browser lifecycle for the Jev Remote contribution and plugin-owned pages. */

import type { Context } from '@deepseek-ai/cordis'
import type { TypertRemoteContribution } from '@deepseek-ai/dsh-typert-protocol'
import type {} from '@deepseek-ai/dsh-api-remotes/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-plugin-manager/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-settings/client'
import type {} from '@deepseek-ai/dsh-client-ui-layout/client'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import type {} from '@himetuki/dsh-neohorse-jev-4b-plugin/remote'
import { createSnapshotStore } from '@deepseek-ai/dsh-client-store'
import type { SupervisionConfigValues } from '../supervision-types.ts'
import type { SelectionConfigValues } from '../selection-types.ts'
import type { OutputAdmissionConfigValues } from '../output-admission-types.ts'
import type { StageNavigationConfigValues } from '../stage-types.ts'
import { JevPage, type JevConfigValues, type JevPageFace } from './JevPage.tsx'
import { JevToast, type JevToastMessage } from './JevToast.tsx'
import { StageNavigation } from './StageNavigation.tsx'
import { watchStageView } from './stage-registration.ts'
import { stageEn, stageZh, type StageLocaleKey } from './stage-locales.ts'
import { en, zh, type JevLocaleKey } from './locales.ts'
import { jevPageRemote, jevStageRemote } from './remote-adapter.ts'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** Jev settings and record-browser copy. */
    'jev.plugin': JevLocaleKey
    /** Session stage navigation copy. */
    'jev.stage': StageLocaleKey
  }
}

const NS = 'jev.plugin'
const STAGE_NS = 'jev.stage'
const PACKAGE = '@himetuki/dsh-neohorse-jev-4b-plugin'
const ENTRY = 'jev'
const SELECTION_ENTRY = 'jev-selection'
const OUTPUT_ENTRY = 'jev-output-admission'

/** Services needed after the generated Jev Remote contribution mounts. */
export const inject = ['remote', 'slots', 'locale', 'configForms']

function registerUi(ctx: Context): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }))
  ctx.effect(() => ctx.locale.register(STAGE_NS, { zh: stageZh, en: stageEn }))
  const form = ctx.configForms.get<JevConfigValues>(ENTRY)
  const selectionForm = ctx.configForms.get<SelectionConfigValues>(SELECTION_ENTRY)
  const outputAdmissionForm = ctx.configForms.get<OutputAdmissionConfigValues>(OUTPUT_ENTRY)
  const supervisionForm = ctx.configForms.get<SupervisionConfigValues>('jev-supervision')
  const stageNavigationForm = ctx.configForms.get<StageNavigationConfigValues>('jev-stage-navigation')
  const toast = createSnapshotStore<JevToastMessage | null>(null)
  let sequence = 0
  const dismiss = () => { toast.set(null) }
  const notifySuccess = (message: string) => { toast.set({ sequence: ++sequence, text: message }) }
  const face: JevPageFace = { form, selectionForm, supervisionForm, outputAdmissionForm, stageNavigationForm, jev: jevPageRemote(ctx.remote.jev), notifySuccess }
  ctx.slots.inject('shell.overlay', () => ctx.slots.register({
    name: 'shell.overlay', id: 'jev.feedback', inject: () => ({ hooks: { jevToast: toast }, dismiss }),
  }, JevToast))
  ctx.effect(() => ctx.configForms.whileServed([ENTRY], () => ctx.slots.inject('plugins.bundle.config', () => ctx.slots.register({
    name: 'plugins.bundle.config',
    key: PACKAGE,
    locale: NS,
    inject: () => face,
  }, JevPage))))
  const stageT = ctx.locale.bind(STAGE_NS)
  const stageRemote = jevStageRemote(ctx.remote.jev)
  ctx.effect(() => watchStageView(form, () => ctx.slots.inject('conversation.view', () => ctx.slots.register({
    name: 'conversation.view', id: 'jev-stage-navigation', order: 20,
    locale: STAGE_NS, label: () => stageT('title'),
    inject: (sessionId) => ({ sessionId, jev: stageRemote }),
  }, StageNavigation))))
}

/**
 * Mount Jev's generated Remote first, then register the bundle page while its settings entry is served.
 * @param ctx - Client runtime with Remote, locale, slots, and config forms.
 * @param contribution - generated Jev Remote namespace.
 * @returns disposer for both Remote and UI registrations.
 */
export async function mountJevUi(ctx: Context, contribution: TypertRemoteContribution): Promise<() => Promise<void>> {
  const disposeRemote = await ctx.remote.$mount(contribution)
  const ui = ctx.inject(['remote.jev', 'slots', 'locale', 'configForms'], registerUi)
  try { await ui } catch (error) { await ui.dispose(); await disposeRemote(); throw error }
  return async () => { await ui.dispose(); await disposeRemote() }
}
