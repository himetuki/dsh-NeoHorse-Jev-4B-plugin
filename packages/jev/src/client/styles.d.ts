/** CSS Modules are compiled and injected by this package's client bundle. */
declare module '*.module.css' {
  const classes: Readonly<Record<string, string>>
  export default classes
}
