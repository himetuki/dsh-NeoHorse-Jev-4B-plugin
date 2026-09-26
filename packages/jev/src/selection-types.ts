/** Profile settings for skill-catalog filtering and glob-result ranking. */
export interface SelectionConfigValues {
  /** Maximum skill summaries shown after Jev filters the catalogue. */
  skillLimit: number
  /** Maximum glob match count eligible for Jev ranking; larger results bypass Jev. */
  fileCandidates: number
  /** Maximum ranked paths shown in a Jev-processed glob result. */
  fileLimit: number
}
