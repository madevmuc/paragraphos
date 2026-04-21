// Shows / Library tab — 3 variations

// Sample watchlist data
const SHOWS = [
  { slug: 'odd-lots',        title: 'Odd Lots',                            on: true,  total: 412, done: 389, pend: 23, feed: 'ok' },
  { slug: 'macro-musings',   title: 'Macro Musings with David Beckworth',  on: true,  total: 298, done: 295, pend: 3,  feed: 'ok' },
  { slug: 'a16z',            title: 'a16z Podcast',                         on: true,  total: 664, done: 660, pend: 4,  feed: 'warn' },
  { slug: 'the-property-pod',title: 'The Property Podcast',                 on: true,  total: 512, done: 490, pend: 22, feed: 'ok' },
  { slug: 'capital-alloc',   title: 'Capital Allocators',                   on: true,  total: 328, done: 328, pend: 0,  feed: 'ok' },
  { slug: 'invest-talk',     title: 'Investor Talk Show',                   on: false, total: 190, done: 140, pend: 50, feed: 'ok' },
  { slug: 'realestate-ger',  title: 'Immobilien-Podcast Deutschland',       on: true,  total: 241, done: 232, pend: 9,  feed: 'ok' },
  { slug: 'valueinv',        title: 'Value Investing with Legends',         on: true,  total: 156, done: 156, pend: 0,  feed: 'ok' },
];

function LibraryStats({ compact }) {
  if (compact) {
    return (
      <div className="mono tiny muted">
        1.423 transcripts · 1.842h audio · 11.840.201 words · 23 pending · 4 failed
      </div>
    );
  }
  return (
    <div className="sk-box" style={{ display: 'flex', gap: 22, alignItems: 'baseline' }}>
      <div><b>Library</b></div>
      <div><b className="mono">1 423</b> transcripts</div>
      <div className="muted">·</div>
      <div><b className="mono">1 842h</b> audio</div>
      <div className="muted">·</div>
      <div><b className="mono">11 840 201</b> words</div>
      <div className="muted">·</div>
      <div><b className="mono">23</b> pending</div>
      <div className="muted">·</div>
      <div><b className="mono">4</b> failed</div>
    </div>
  );
}

// ── A: tabs + dense table (current-style, cleaned) ───────────
function ShowsA({ showStatusbar }) {
  return (
    <MacWindow title="Paragraphos" height={520} caption={
      "A · Tabs up top, dense table. Closest to today. Progress reads best at a glance; status bar keeps queue state in every screen."
    }>
      <div className="toolbar" style={{ gap: 4, padding: '6px 10px' }}>
        {['Shows','Queue','Failed','Settings'].map((t,i)=>(
          <div key={t} style={{
            padding: '4px 10px',
            borderRadius: 5,
            background: i===0 ? 'var(--accent-tint)' : 'transparent',
            color: i===0 ? 'var(--ink)' : 'var(--ink-3)',
            fontWeight: i===0 ? 600 : 400,
            fontSize: 13,
          }}>{t}</div>
        ))}
      </div>
      <div style={{ padding: 14, flex: 1, display: 'flex', flexDirection: 'column', gap: 10, overflow: 'hidden' }}>
        <LibraryStats />
        <div style={{ flex: 1, overflow: 'hidden', border: '1.5px solid var(--line-soft)', borderRadius: 6 }}>
          <table className="wf-table">
            <thead>
              <tr>
                <th style={{width:40}}>On</th>
                <th>Title</th>
                <th style={{width:90}}>Progress</th>
                <th style={{width:70}} className="mono tiny">Pending</th>
                <th style={{width:70}}>Feed</th>
              </tr>
            </thead>
            <tbody>
              {SHOWS.slice(0,7).map((s,i)=>(
                <tr key={s.slug}>
                  <td>{s.on ? '●' : <span className="dim">○</span>}</td>
                  <td>
                    <div style={{fontWeight:500}}>{s.title}</div>
                    <div className="mono tiny muted">{s.slug}</div>
                  </td>
                  <td>
                    <div className="mono tiny">{s.done}/{s.total}</div>
                    <Progress pct={Math.round(s.done/s.total*100)}/>
                  </td>
                  <td className="mono tiny">{s.pend}</td>
                  <td>{s.feed==='ok' ? <Pill kind="ok">ok</Pill> : <Pill kind="fail">stale</Pill>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button className="btn primary">+ Add podcast</button>
          <button className="btn">Add episodes</button>
          <button className="btn">Check now</button>
          <div className="grow"/>
          <button className="btn ghost">Check feeds</button>
          <button className="btn ghost">Rescan library</button>
        </div>
      </div>
      <StatusBar visible={showStatusbar}/>
    </MacWindow>
  );
}

// ── B: left sidebar + same table as A ────────────
function ShowsB({ showStatusbar }) {
  return (
    <MacWindow title="Paragraphos" height={520} caption={
      "B · Sidebar nav with live counts; same table as A. Shows how A's density reads when the primary nav lives on the side instead of up top."
    }>
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <div className="sidebar" style={{ width: 160 }}>
          <div className="side-group">Library</div>
          <div className="item active">Shows <span className="count">16</span></div>
          <div className="item">Queue <span className="count">23</span></div>
          <div className="item">Failed <span className="count">4</span></div>
          <div className="item">All episodes</div>
          <div className="side-group" style={{marginTop:14}}>System</div>
          <div className="item">Settings</div>
          <div className="item">Logs</div>
          <div className="item">About</div>
        </div>
        <div style={{ flex: 1, padding: 14, display: 'flex', flexDirection: 'column', gap: 10, overflow: 'hidden', position: 'relative' }}>
          <LibraryStats />
          <div className="row" style={{gap: 6}}>
            <div className="mono tiny muted grow">Showing 7 of 16 · filtered by <b>enabled</b>, <b>feed:ok</b></div>
            <button className="btn" style={{position: 'relative'}}>
              ▾ Filter <span className="pill" style={{padding:'0 5px', marginLeft:4, fontSize:10}}>2</span>
            </button>
          </div>
          <div style={{ flex: 1, overflow: 'hidden', border: '1.5px solid var(--line-soft)', borderRadius: 6 }}>
            <table className="wf-table">
              <thead>
                <tr>
                  <th style={{width:40}}>On</th>
                  <th>Title</th>
                  <th style={{width:90}}>Progress</th>
                  <th style={{width:70}} className="mono tiny">Pending</th>
                  <th style={{width:70}}>Feed</th>
                </tr>
              </thead>
              <tbody>
                {SHOWS.slice(0,7).map((s)=>(
                  <tr key={s.slug}>
                    <td>{s.on ? '●' : <span className="dim">○</span>}</td>
                    <td>
                      <div style={{fontWeight:500}}>{s.title}</div>
                      <div className="mono tiny muted">{s.slug}</div>
                    </td>
                    <td>
                      <div className="mono tiny">{s.done}/{s.total}</div>
                      <Progress pct={Math.round(s.done/s.total*100)}/>
                    </td>
                    <td className="mono tiny">{s.pend}</td>
                    <td>{s.feed==='ok' ? <Pill kind="ok">ok</Pill> : <Pill kind="fail">stale</Pill>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button className="btn primary">+ Add podcast</button>
            <button className="btn">Add episodes</button>
            <button className="btn">Check now</button>
            <div className="grow"/>
            <button className="btn ghost">Check feeds</button>
          </div>
          {/* Filter popover (shown open for the mock) */}
          <div style={{
            position: 'absolute', top: 78, right: 14, width: 220,
            background: 'var(--surface)', border: '1.5px solid var(--line)',
            borderRadius: 8, padding: 12, boxShadow: '0 6px 20px rgba(0,0,0,0.08)',
            zIndex: 2, fontSize: 12,
          }}>
            <div style={{fontWeight:600, marginBottom:6}}>Filter shows</div>
            <div style={{display:'flex', flexDirection:'column', gap:4}}>
              <label className="row" style={{gap:6}}><input type="checkbox" defaultChecked/> Enabled only</label>
              <label className="row" style={{gap:6}}><input type="checkbox"/> Has pending episodes</label>
              <label className="row" style={{gap:6}}><input type="checkbox"/> Has failed episodes</label>
              <div className="tiny muted" style={{marginTop:6, textTransform:'uppercase', letterSpacing:0.5, fontSize:10}}>Feed status</div>
              <label className="row" style={{gap:6}}><input type="checkbox" defaultChecked/> ✅ ok</label>
              <label className="row" style={{gap:6}}><input type="checkbox"/> ⚠ stale</label>
              <label className="row" style={{gap:6}}><input type="checkbox"/> ✖ unreachable</label>
              <div className="tiny muted" style={{marginTop:6, textTransform:'uppercase', letterSpacing:0.5, fontSize:10}}>Search</div>
              <div className="sk-box" style={{padding:'3px 6px'}}>macro…</div>
            </div>
            <div className="row" style={{gap:6, marginTop:10}}>
              <button className="btn ghost" style={{fontSize:11}}>Clear</button>
              <div className="grow"/>
              <button className="btn primary" style={{fontSize:11}}>Apply</button>
            </div>
          </div>
        </div>
      </div>
      <StatusBar visible={showStatusbar}/>
    </MacWindow>
  );
}

// ── C: single unified view, no tabs ─────────────────────────
function ShowsC({ showStatusbar }) {
  return (
    <MacWindow title="Paragraphos" height={520} caption={
      "C · No tabs — library is the home. Queue + failed collapse into inline banners at the top. Settings opens as a sheet (see dialog below)."
    }>
      <div className="toolbar" style={{ gap: 10, padding: '10px 14px' }}>
        <div style={{ fontWeight: 600, fontSize: 14 }}>Library</div>
        <div className="mono tiny muted grow">16 shows · 1.423 transcripts</div>
        <button className="btn">Settings</button>
        <button className="btn">Logs</button>
        <button className="btn primary">Check now</button>
      </div>
      <div style={{ padding: 14, flex: 1, display: 'flex', flexDirection: 'column', gap: 10, overflow: 'hidden' }}>
        {/* inline running banner */}
        <div className="sk-box" style={{
          background: 'var(--accent-tint)',
          borderColor: 'var(--accent)',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '8px 12px'
        }}>
          <Pill kind="running">running</Pill>
          <span><b className="mono">3/12</b></span>
          <div style={{ flex: 1, maxWidth: 280 }}><Progress pct={25}/></div>
          <span className="muted tiny">ETA 52m · finish ≈ 10:24</span>
          <button className="btn ghost" style={{marginLeft:'auto'}}>Pause</button>
          <button className="btn ghost">Stop</button>
        </div>
        {/* failed banner */}
        <div className="sk-box" style={{
          display: 'flex', alignItems: 'center', gap: 12, padding: '6px 12px',
          borderColor: 'var(--line-soft)'
        }}>
          <span style={{color:'var(--danger)', fontSize: 14}}>⚠</span>
          <span className="tiny"><b>4 failed episodes</b> — view details</span>
          <div className="grow"/>
          <button className="btn ghost">Review</button>
        </div>
        <div style={{ flex: 1, overflow: 'auto' }}>
          <table className="wf-table">
            <thead>
              <tr>
                <th style={{width:32}}></th>
                <th>Show</th>
                <th style={{width:120}}>Progress</th>
                <th style={{width:80}}>Pending</th>
                <th style={{width:60}}>Feed</th>
              </tr>
            </thead>
            <tbody>
              {SHOWS.map(s=>(
                <tr key={s.slug}>
                  <td>{s.on ? '●' : <span className="dim">○</span>}</td>
                  <td>{s.title}<div className="mono tiny muted">{s.slug}</div></td>
                  <td>
                    <div className="row" style={{gap:6}}>
                      <Progress pct={Math.round(s.done/s.total*100)}/>
                      <span className="mono tiny muted" style={{whiteSpace:'nowrap'}}>{s.done}/{s.total}</span>
                    </div>
                  </td>
                  <td className="mono tiny">{s.pend}</td>
                  <td>{s.feed==='ok' ? '✓' : <span style={{color:'var(--danger)'}}>⚠</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <StatusBar visible={showStatusbar}/>
    </MacWindow>
  );
}

function ShowsPage({ showStatusbar }) {
  return (
    <div className="page">
      <div className="page-head">
        <h1>Shows · library</h1>
        <div className="sub">Main watchlist — where the user lives 80% of the time. Variations probe nav shape + density + how the queue bleeds into the home view.</div>
      </div>
      <div className="variation-row">
        <div><VariationLabel letter="A" name="Tabs + dense table" note="evolution of today"/>
          <ShowsA showStatusbar={showStatusbar}/>
        </div>
        <div><VariationLabel letter="B" name="Sidebar + cards" note="roomier, more visual"/>
          <ShowsB showStatusbar={showStatusbar}/>
        </div>
        <div><VariationLabel letter="C" name="Unified view" note="no tabs, inline banners"/>
          <ShowsC showStatusbar={showStatusbar}/>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { ShowsPage });
