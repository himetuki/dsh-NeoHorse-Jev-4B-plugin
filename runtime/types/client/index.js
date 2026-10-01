/** Browser entry for Jev's external Remote and Plugins bundle page. */
import jevRemote from '@himetuki/dsh-neohorse-jev-4b-plugin/remote';
import { mountJevUi } from "./mount.js";
export { inject } from "./mount.js";
/** Activate Jev's browser contribution. */
export async function apply(ctx) {
    return await mountJevUi(ctx, jevRemote);
}
//# sourceMappingURL=index.js.map