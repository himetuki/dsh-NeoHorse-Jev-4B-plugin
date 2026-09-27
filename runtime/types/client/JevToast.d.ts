/** Frame-wide feedback for completed Jev settings writes. */
import type { SnapshotStore } from '@deepseek-ai/dsh-client-store';
import type { InjectFace, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots';
/** One transient success message retained outside the plugin detail page. */
export interface JevToastMessage {
    sequence: number;
    text: string;
}
/** Store and dismissal injected by the Jev browser registration. */
export interface JevToastFace {
    hooks: {
        jevToast: SnapshotStore<JevToastMessage | null>;
    };
    dismiss: () => void;
}
/** Render the current message in the Host overlay. */
export declare function JevToast({ useJevToast, dismiss }: PropsRuntime<'shell.overlay'> & InjectFace<JevToastFace>): import("react/jsx-runtime").JSX.Element | null;
//# sourceMappingURL=JevToast.d.ts.map