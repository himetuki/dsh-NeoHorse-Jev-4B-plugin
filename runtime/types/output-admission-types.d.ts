/** Profile limits for model-visible command and test log admission. */
export interface OutputAdmissionConfigValues {
    generalMinChars: number;
    testMinChars: number;
    generalBlockChars: number;
    maxGeneralBlocks: number;
    maxTestCandidates: number;
    maxRequestChars: number;
    maxChunks: number;
    maxTaskChars: number;
    waitMs: number;
    omitProbability: number;
    minSavedChars: number;
    minSavedRatio: number;
    slowTestMs: number;
    duplicateMinLines: number;
    duplicateMinChars: number;
}
//# sourceMappingURL=output-admission-types.d.ts.map