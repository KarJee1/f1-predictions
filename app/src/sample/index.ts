// A real snapshot of the backend's output (Mexico City GP week, 2026), bundled so the UI can be
// worked on without the API. Only used when EXPO_PUBLIC_USE_SAMPLE_DATA=1.
const docs: Record<string, unknown> = {
  'v1/meta.json': require('./meta.json'),
  'v1/news.json': require('./news.json'),
  'v1/standings.json': require('./standings.json'),
  'v1/accuracy/2026.json': require('./accuracy.json'),
  'v1/races/2026/19/prediction.json': require('./prediction.json'),
  'v1/races/2026/18/results.json': require('./results-18.json'),
  'v1/races/2026/17/results.json': require('./results-17.json'),
};

export function sample(path: string): unknown {
  return docs[path];
}
