export function selectAnalysisRun(runs, requestedId) {
  if (requestedId) return runs.find(run => run.id === requestedId) || null
  return runs[0] || null
}
