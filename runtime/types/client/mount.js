/** Browser lifecycle for the Jev Remote contribution and plugin-owned pages. */
import { createSnapshotStore } from '@deepseek-ai/dsh-client-store';
import { JevPage } from "./JevPage.js";
import { JevToast } from "./JevToast.js";
import { en, zh } from "./locales.js";
import { jevPageRemote } from "./remote-adapter.js";
const NS = 'jev.plugin';
const PACKAGE = '@dsh-jev/plugin';
const ENTRY = 'jev';
const SELECTION_ENTRY = 'jev-selection';
const OUTPUT_ENTRY = 'jev-output-admission';
/** Services needed after the generated Jev Remote contribution mounts. */
export const inject = ['remote', 'slots', 'locale', 'configForms'];
function registerUi(ctx) {
    ctx.effect(() => ctx.locale.register(NS, { zh, en }));
    const form = ctx.configForms.get(ENTRY);
    const selectionForm = ctx.configForms.get(SELECTION_ENTRY);
    const outputAdmissionForm = ctx.configForms.get(OUTPUT_ENTRY);
    const supervisionForm = ctx.configForms.get('jev-supervision');
    const toast = createSnapshotStore(null);
    let sequence = 0;
    const dismiss = () => { toast.set(null); };
    const notifySuccess = (message) => { toast.set({ sequence: ++sequence, text: message }); };
    const face = { form, selectionForm, supervisionForm, outputAdmissionForm, jev: jevPageRemote(ctx.remote.jev), notifySuccess };
    ctx.slots.inject('shell.overlay', () => ctx.slots.register({
        name: 'shell.overlay', id: 'jev.feedback', inject: () => ({ hooks: { jevToast: toast }, dismiss }),
    }, JevToast));
    ctx.effect(() => ctx.configForms.whileServed([ENTRY], () => ctx.slots.inject('plugins.bundle.config', () => ctx.slots.register({
        name: 'plugins.bundle.config',
        key: PACKAGE,
        locale: NS,
        inject: () => face,
    }, JevPage))));
}
/**
 * Mount Jev's generated Remote first, then register the bundle page while its settings entry is served.
 * @param ctx - Client runtime with Remote, locale, slots, and config forms.
 * @param contribution - generated Jev Remote namespace.
 * @returns disposer for both Remote and UI registrations.
 */
export async function mountJevUi(ctx, contribution) {
    const disposeRemote = await ctx.remote.$mount(contribution);
    const ui = ctx.inject(['remote.jev', 'slots', 'locale', 'configForms'], registerUi);
    try {
        await ui;
    }
    catch (error) {
        await ui.dispose();
        await disposeRemote();
        throw error;
    }
    return async () => { await ui.dispose(); await disposeRemote(); };
}
//# sourceMappingURL=mount.js.map