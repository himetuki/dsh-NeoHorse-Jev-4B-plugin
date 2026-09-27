/** Convert the generated Jev Remote result envelope to page commands. */
function unwrap(result) {
    if (!result.ok)
        throw result.error;
    return result.value;
}
/**
 * Adapt every Jev Remote call to the page's Promise-of-value API.
 * @param remote - generated Remote namespace, whose carrier and Host failures resolve as `RemoteResult`.
 * @returns page commands that resolve to business values or reject with the Remote failure.
 */
export function jevPageRemote(remote) {
    return {
        listFeatures: async () => unwrap(await remote.listFeatures()),
        listRecords: async (filter) => unwrap(await remote.listRecords(filter)),
        getRecord: async (id) => unwrap(await remote.getRecord(id)),
        testConnection: async (signal) => unwrap(await remote.testConnection(signal)),
        getCredentialStatus: async () => unwrap(await remote.getCredentialStatus()),
        setCredential: async (value) => unwrap(await remote.setCredential(value)),
    };
}
//# sourceMappingURL=remote-adapter.js.map