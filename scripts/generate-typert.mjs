import { resolve } from 'node:path'
import { typertPlugin } from '@deepseek-ai/dsh-typert-generator/tsdown'

typertPlugin({ mode: 'workspace', faces: ['host'] })
  .writeBundle({ dir: resolve('lib') })
