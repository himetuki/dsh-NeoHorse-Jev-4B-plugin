import { defineConfig } from 'tsdown'

export default defineConfig({
  entry: ['packages/jev/lib/types/index.js', 'packages/jev/lib/types/selection.js', 'packages/jev/lib/types/supervision.js', 'packages/jev/lib/types/instructions.js', 'packages/jev/lib/types/shared-findings.js', 'packages/jev/lib/types/interjection.js', 'packages/jev/lib/types/output-admission.js', 'packages/jev/lib/types/workspace-approval.js', 'packages/jev/lib/types/stage-navigation.js', 'packages/jev/lib/types/stage-types.js'],
  outDir: 'packages/jev/lib',
  format: ['esm'],
  platform: 'node',
  target: 'es2024',
  fixedExtension: false,
  dts: false,
  clean: false,
  external: [/^@deepseek-ai\//, /^@himetuki\/dsh-neohorse-jev-4b-plugin\//, /^react(?:-dom)?(?:\/.*)?$/],
})
