import { type Domain } from '@deepseek-ai/dsh-storage-domain';
import type { StageAnalysisRecord } from './stage-types.ts';
/** One profile never shares auxiliary classifications with another profile. */
export declare function stageStoreSpec(profileDir: string): {
    name: string;
    version: number;
    layout: "per-record";
    tables: {
        records: import("@deepseek-ai/dsh-storage-domain").DomainTableSpec<string, StageAnalysisRecord>;
    };
};
export declare class StageStore {
    private readonly domain;
    private constructor();
    static open(facility: {
        open: (spec: ReturnType<typeof stageStoreSpec>) => Promise<Domain<ReturnType<typeof stageStoreSpec>>>;
    }, profileDir: string): Promise<StageStore>;
    all(): StageAnalysisRecord[];
    forSession(sessionId: string): StageAnalysisRecord[];
    save(record: StageAnalysisRecord): Promise<void>;
    close(): Promise<void>;
}
//# sourceMappingURL=stage-store.d.ts.map