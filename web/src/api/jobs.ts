/** The Runs page lists search jobs; evaluate and validate jobs belong to their case. */
export const searchJobs = <T extends { kind: string }>(jobs: T[]): T[] => jobs.filter((j) => j.kind === "search")
