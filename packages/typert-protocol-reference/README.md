# Typert build reference

The build copies the unmodified `lib/types/*.d.ts` declarations from the installed `@deepseek-ai/dsh-typert-protocol@0.2.0-rc.2` into `src/`. The official Typert generator indexes these declarations through the Host project references while analyzing the external Jev plugin. This private directory is excluded from pnpm workspaces and the plugin package; runtime imports continue to use the installed peer package.
