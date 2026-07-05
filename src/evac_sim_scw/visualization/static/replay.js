export async function loadReplay() {
  const [metadataResponse, replayResponse] = await Promise.all([
    fetch('/data/replay_metadata.json'), fetch('/data/replay.jsonl')
  ]);
  if (!metadataResponse.ok || !replayResponse.ok) throw new Error('Replay data could not be loaded');
  const metadata = await metadataResponse.json();
  const text = await replayResponse.text();
  const frames = text.trim().split(/\r?\n/).filter(Boolean).map(JSON.parse);
  return { metadata, frames };
}

export function framePair(frames, time) {
  let low = 0, high = frames.length - 1;
  while (low < high) {
    const mid = Math.ceil((low + high) / 2);
    if (frames[mid].t <= time) low = mid; else high = mid - 1;
  }
  const a = frames[low];
  const b = frames[Math.min(low + 1, frames.length - 1)];
  const alpha = b.t === a.t ? 0 : Math.max(0, Math.min(1, (time - a.t) / (b.t - a.t)));
  return { a, b, alpha, index: low };
}
