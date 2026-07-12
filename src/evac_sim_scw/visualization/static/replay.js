const METADATA_URL = '/data/replay_metadata.json';
const REPLAY_URL = '/data/replay.jsonl';

export async function loadReplay() {
  // Fetch and decode the metadata plus newline-delimited replay frames.
  const [metadataResponse, replayResponse] = await Promise.all([
    fetch(METADATA_URL),
    fetch(REPLAY_URL),
  ]);

  if (!metadataResponse.ok || !replayResponse.ok) {
    throw new Error(
      `Viewer data could not be loaded (metadata HTTP ${metadataResponse.status}, replay HTTP ${replayResponse.status})`,
    );
  }

  const metadata = await metadataResponse.json();
  const replayText = await replayResponse.text();
  const frames = replayText
    .trim()
    .split(/\r?\n/)
    .filter(Boolean)
    .map(JSON.parse);

  if (frames.length === 0) {
    throw new Error('Replay does not contain any frames');
  }

  return { metadata, frames };
}

export function framePair(frames, time) {
  // Locate the adjacent frames used to interpolate a requested time.
  let low = 0;
  let high = frames.length - 1;

  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (frames[middle].t <= time) {
      low = middle;
    } else {
      high = middle - 1;
    }
  }

  const current = frames[low];
  const next = frames[Math.min(low + 1, frames.length - 1)];
  const alpha = next.t === current.t
    ? 0
    : Math.max(0, Math.min(1, (time - current.t) / (next.t - current.t)));

  return { a: current, b: next, alpha, index: low };
}
