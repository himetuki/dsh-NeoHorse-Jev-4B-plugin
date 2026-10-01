/** Browser entry for Jev's external Remote and Plugins bundle page. */

import type { Context } from '@deepseek-ai/cordis'
import jevRemote from '@himetuki/dsh-neohorse-jev-4b-plugin/remote'
import { mountJevUi } from './mount.ts'

export { inject } from './mount.ts'

/** Activate Jev's browser contribution. */
export async function apply(ctx: Context): Promise<() => Promise<void>> {
  return await mountJevUi(ctx, jevRemote)
}
