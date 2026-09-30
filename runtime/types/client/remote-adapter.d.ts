/** Convert the generated Jev Remote result envelope to page commands. */
import type { Context } from '@deepseek-ai/cordis';
import type { JevPageRemote } from './JevPage.tsx';
import type { StageNavigationRemote } from './StageNavigation.tsx';
/** Generated Jev namespace as installed on the shared Client Remote. */
export type JevWireRemote = Context['remote']['jev'];
/**
 * Adapt every Jev Remote call to the page's Promise-of-value API.
 * @param remote - generated Remote namespace, whose carrier and Host failures resolve as `RemoteResult`.
 * @returns page commands that resolve to business values or reject with the Remote failure.
 */
export declare function jevPageRemote(remote: JevWireRemote): JevPageRemote;
/** Adapt the Session stage commands while retaining their Host authorization. */
export declare function jevStageRemote(remote: JevWireRemote): StageNavigationRemote;
//# sourceMappingURL=remote-adapter.d.ts.map