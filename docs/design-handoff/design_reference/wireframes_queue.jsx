// Queue tab — running progress, ETA. This is the "hero moment".

// ── A: status-bar-only, minimal chrome ──
function QueueA({ showStatusbar }) {
  return (
    <MacWindow title="Paragraphos — Queue" height={520} caption={
      "A · Minimal. A single big progress row on top + table of what's next. ETA lives in the status bar only. Least screen real-estate."
    }>
      <div className="toolbar" style={{ padding: '6px 10px', gap: 4 }}>
        {['Shows','Queue','Failed','Settings'].map((t,i)=>(
          <div key={t} style={{
            padding: '4px 10px', borderRadius: 5, fontSize: 13,
            background: i===1 ? 'var(--accent-tint)' : 'transparent',
            color: i===1 ? 'var(--ink)' : 'var(--ink-3)',
            fontWeight: i===1 ? 600 : 400,
          }}>{t}</div>
        ))}
      </div>
      <div style={{ padding: 14, flex: 1, display: 'flex', flexDirection: 'column', gap: 10, overflow: 'hidden' }}>
        <div className="sk-box" style={{ padding: '10px 14px' }}>
          <div className="row">
            <Pill kind="running">running</Pill>
            <b className="mono">3/12</b>
            <div className="grow" style={{ maxWidth: 320 }}><Progress pct={25}/></div>
            <button className="btn">Pause</button>
            <button className="btn">Stop</button>
          </div>
        </div>
        <div style={{ flex: 1, overflow: 'auto', border: '1.5px solid var(--line-soft)', borderRadius: 6 }}>
          <table className="wf-table">
            <thead><tr>
              <th>Show</th><th>Pub date</th><th>Title</th><th style={{width:110}}>Status</th>
            </tr></thead>
            <tbody>
              <tr>
                <td>odd-lots</td>
                <td className="mono tiny">2026-04-18</td>
                <td>
                  <div>The weird cargo-ship market right now</div>
                  <div className="mono tiny muted" style={{marginTop:2}}>whisper · seg 44/71 · 4m 12s elapsed · ~2m 38s left</div>
                </td>
                <td><Pill kind="running">transcribing · 62%</Pill></td>
              </tr>
              <tr>
                <td>a16z</td>
                <td className="mono tiny">2026-04-19</td>
                <td>
                  <div>What's next for on-device ML</div>
                  <div className="mono tiny muted" style={{marginTop:2}}>mp3 · 42 / 238 MB · 8.2 MB/s · ~24s left</div>
                </td>
                <td><Pill kind="running">downloading · 18%</Pill></td>
              </tr>
              <tr><td>macro-musings</td><td className="mono tiny">2026-04-17</td><td>Nominal GDP targeting revisited</td><td><Pill>pending</Pill></td></tr>
              <tr><td>the-property-pod</td><td className="mono tiny">2026-04-16</td><td>Yields in mid-tier German cities</td><td><Pill>pending</Pill></td></tr>
              <tr><td>odd-lots</td><td className="mono tiny">2026-04-15</td><td>Why copper prices are where they are</td><td><Pill>pending</Pill></td></tr>
              <tr><td>a16z</td><td className="mono tiny">2026-04-14</td><td>Climate tech, year 3</td><td><Pill>pending</Pill></td></tr>
            </tbody>
          </table>
        </div>
      </div>
      <StatusBar visible={showStatusbar}/>
    </MacWindow>
  );
}

// ── B: big hero panel with every number surfaced ──
function QueueB({ showStatusbar }) {
  return (
    <MacWindow title="Paragraphos — Queue" height={520} caption={
      "B · Hero panel. All numbers — started, elapsed, per-ep avg, ETA, finish — laid out as a dashboard. Best when actively watching a long run."
    }>
      <div className="toolbar" style={{ padding: '6px 10px', gap: 4 }}>
        {['Shows','Queue','Failed','Settings'].map((t,i)=>(
          <div key={t} style={{
            padding: '4px 10px', borderRadius: 5, fontSize: 13,
            background: i===1 ? 'var(--accent-tint)' : 'transparent',
            color: i===1 ? 'var(--ink)' : 'var(--ink-3)',
            fontWeight: i===1 ? 600 : 400,
          }}>{t}</div>
        ))}
      </div>
      <div style={{ padding: 14, flex: 1, display: 'flex', flexDirection: 'column', gap: 12, overflow: 'hidden' }}>
        <div style={{
          border: '1.5px solid var(--line)',
          borderRadius: 10,
          padding: 16,
          display: 'grid',
          gridTemplateColumns: 'auto 1fr',
          gap: 18,
          alignItems: 'center',
        }}>
          <div style={{ width: 110, height: 110, borderRadius: '50%', border: '4px solid var(--accent)', borderRightColor: 'var(--line-soft)', borderBottomColor: 'var(--line-soft)', display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', transform: 'rotate(-45deg)' }}>
            <div style={{ transform: 'rotate(45deg)', textAlign: 'center' }}>
              <div className="mono" style={{ fontSize: 22, fontWeight: 700 }}>3/12</div>
              <div className="tiny muted">25%</div>
            </div>
          </div>
          <div>
            <div className="row" style={{ gap: 10, marginBottom: 8 }}>
              <Pill kind="running">running</Pill>
              <b style={{ fontSize: 15 }}>odd-lots · The weird cargo-ship market</b>
              <div className="grow"/>
              <button className="btn">Pause</button>
              <button className="btn">Stop</button>
            </div>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap: 14,
              marginTop: 6,
            }}>
              <Stat label="started"  value="09:14" sub="Mon · Apr 20, 2026"/>
              <Stat label="elapsed"  value="18m 02s"/>
              <Stat label="per ep."  value="4m 31s" sub="(est. 5m 40s)"/>
              <Stat label="finish ≈" value="10:24" sub="Mon · in 52m — before lunch"/>
            </div>
          </div>
        </div>
        <div style={{ flex: 1, overflow: 'auto', border: '1.5px solid var(--line-soft)', borderRadius: 6 }}>
          <table className="wf-table">
            <thead><tr><th>Show</th><th>Title</th><th style={{width:110}}>Status</th></tr></thead>
            <tbody>
              <tr><td>a16z</td><td>What's next for on-device ML</td><td><Pill kind="running">downloading</Pill></td></tr>
              <tr><td>macro-musings</td><td>Nominal GDP targeting revisited</td><td><Pill>pending</Pill></td></tr>
              <tr><td>the-property-pod</td><td>Yields in mid-tier German cities</td><td><Pill>pending</Pill></td></tr>
              <tr><td>odd-lots</td><td>Why copper prices are where they are</td><td><Pill>pending</Pill></td></tr>
            </tbody>
          </table>
        </div>
      </div>
      <StatusBar visible={showStatusbar}/>
    </MacWindow>
  );
}

function Stat({ label, value, sub }) {
  return (
    <div>
      <div className="tiny muted" style={{ textTransform: 'uppercase', letterSpacing: 0.5, fontSize: 10 }}>{label}</div>
      <div className="mono" style={{ fontSize: 15, fontWeight: 600, marginTop: 2 }}>{value}</div>
      {sub && <div className="tiny muted">{sub}</div>}
    </div>
  );
}

// ── C: timeline list — each episode a row that fills with progress ──
function QueueC({ showStatusbar }) {
  const rows = [
    { show: 'odd-lots', title: 'The weird cargo-ship market right now', state: 'transcribing', pct: 62,
      step: 'whisper · seg 44/71', extra: '4m 12s elapsed · ~2m 38s left · model large-v3-turbo' },
    { show: 'a16z', title: "What's next for on-device ML", state: 'downloading', pct: 18,
      step: 'mp3 · 42 / 238 MB', extra: '8.2 MB/s · ~24s left' },
    { show: 'macro-musings', title: 'Nominal GDP targeting revisited', state: 'pending', pct: 0,
      step: 'queued', extra: 'waiting — position 1 of 9' },
    { show: 'the-property-pod', title: 'Yields in mid-tier German cities', state: 'pending', pct: 0,
      step: 'queued', extra: 'waiting — position 2 of 9' },
    { show: 'odd-lots', title: 'Why copper prices are where they are', state: 'pending', pct: 0,
      step: 'queued', extra: 'waiting — position 3 of 9' },
    { show: 'a16z', title: 'Climate tech, year 3', state: 'pending', pct: 0,
      step: 'queued', extra: 'waiting — position 4 of 9' },
    { show: 'macro-musings', title: 'The Fed\'s term premium problem', state: 'done', pct: 100,
      step: 'done', extra: '5m 12s · 8 742 words · 09:18' },
    { show: 'odd-lots', title: 'Hedge fund crowding, now with data', state: 'done', pct: 100,
      step: 'done', extra: '4m 48s · 7 320 words · 09:13' },
    { show: 'capital-alloc', title: 'Talking taxes with David Swensen', state: 'done', pct: 100,
      step: 'done', extra: '6m 02s · 10 118 words · 09:07' },
  ];
  return (
    <MacWindow title="Paragraphos — Queue" height={520} caption={
      "C · Timeline. Each episode is a row; its row-fill reflects live progress. Done items greyed above, in-flight highlighted, pending stacked below."
    }>
      <div className="toolbar" style={{ padding: '6px 10px', gap: 4 }}>
        {['Shows','Queue','Failed','Settings'].map((t,i)=>(
          <div key={t} style={{
            padding: '4px 10px', borderRadius: 5, fontSize: 13,
            background: i===1 ? 'var(--accent-tint)' : 'transparent',
            color: i===1 ? 'var(--ink)' : 'var(--ink-3)',
            fontWeight: i===1 ? 600 : 400,
          }}>{t}</div>
        ))}
      </div>
      <div style={{ padding: 14, flex: 1, display: 'flex', flexDirection: 'column', gap: 10, overflow: 'hidden' }}>
        <div className="row" style={{ gap: 12 }}>
          <b>3 / 12</b>
          <span className="mono tiny muted">ETA 52m · finish ≈ 10:24</span>
          <div className="grow"/>
          <button className="btn">Pause</button>
          <button className="btn">Stop</button>
        </div>
        <div style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 4 }}>
          {rows.map((r, i) => (
            <div key={i} style={{
              position: 'relative',
              border: '1.5px solid var(--line-soft)',
              borderRadius: 6,
              padding: '8px 10px',
              overflow: 'hidden',
              opacity: r.state === 'done' ? 0.5 : 1,
              borderColor: r.state === 'transcribing' || r.state === 'downloading' ? 'var(--accent)' : 'var(--line-soft)',
            }}>
              {r.pct > 0 && r.state !== 'done' && (
                <div style={{
                  position: 'absolute', inset: 0,
                  width: r.pct + '%',
                  background: 'var(--accent-tint)',
                  pointerEvents: 'none',
                }}/>
              )}
              <div className="row" style={{ position: 'relative', gap: 10, alignItems: 'flex-start' }}>
                <div style={{ width: 16, paddingTop: 2 }}>
                  {r.state === 'done' && '✓'}
                  {r.state === 'transcribing' && '●'}
                  {r.state === 'downloading' && '↓'}
                  {r.state === 'pending' && <span className="dim">○</span>}
                </div>
                <div className="mono tiny muted" style={{ width: 110, paddingTop: 2 }}>{r.show}</div>
                <div className="grow">
                  <div style={{ fontWeight: 500, fontSize: 13 }}>{r.title}</div>
                  <div className="mono tiny muted" style={{ marginTop: 2 }}>
                    {r.step}{r.extra ? <> · {r.extra}</> : null}
                  </div>
                </div>
                <div className="tiny muted" style={{ paddingTop: 2 }}>{r.state}</div>
                {r.pct > 0 && r.state !== 'done' && (
                  <div className="mono tiny" style={{ paddingTop: 2, width: 36, textAlign: 'right' }}>{r.pct}%</div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
      <StatusBar visible={showStatusbar}/>
    </MacWindow>
  );
}

function QueuePage({ showStatusbar }) {
  return (
    <div className="page">
      <div className="page-head">
        <h1>Queue · live progress</h1>
        <div className="sub">The hero moment. Variations trade-off "how much real-estate the run deserves" vs. "how quickly you can see what's next".</div>
      </div>
      <div className="variation-row">
        <div><VariationLabel letter="A" name="Minimal bar" note="restrained, fast"/>
          <QueueA showStatusbar={showStatusbar}/>
        </div>
        <div><VariationLabel letter="B" name="Hero dashboard" note="every number surfaced"/>
          <QueueB showStatusbar={showStatusbar}/>
        </div>
        <div><VariationLabel letter="C" name="Timeline" note="progress per row"/>
          <QueueC showStatusbar={showStatusbar}/>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { QueuePage });
