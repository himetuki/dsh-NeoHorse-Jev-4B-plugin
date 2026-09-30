/** Session-bound, read-only source viewer with explicit Jev stage analysis actions. */
import type { InjectFace, PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots';
import type { StageAnalysisRecord, StageAnalysisRequest, StageBatchState, StageNavigationSnapshot } from '../stage-types.ts';
/** Host commands available only for the active, authorized Session. */
export interface StageNavigationRemote {
    getStageNavigation(sessionId: string, signal: AbortSignal): Promise<StageNavigationSnapshot>;
    startStageAnalysis(request: StageAnalysisRequest): Promise<StageBatchState>;
    cancelStageAnalysis(batchId: string): Promise<void>;
    getStageAnalysisRecord(sessionId: string, stepId: string, recordId?: string): Promise<StageAnalysisRecord | null>;
}
/** Values supplied by the conversation view registration. */
export interface StageNavigationFace {
    sessionId: string;
    jev: StageNavigationRemote;
}
/** Locale and Host Remote face of the Session view. */
export type StageNavigationProps = PropsRuntime<'conversation.view'> & PropsLocale<'jev.stage'> & InjectFace<StageNavigationFace>;
/** Render the Host's full authorized Session history and persisted Jev annotations. */
export declare function StageNavigation({ sessionId, jev, t, openView }: StageNavigationProps): import("react/jsx-runtime").JSX.Element | null;
//# sourceMappingURL=StageNavigation.d.ts.map