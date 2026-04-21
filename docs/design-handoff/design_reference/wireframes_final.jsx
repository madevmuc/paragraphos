// Final clean direction — the picked patterns, one screen each.
// Uses: tabs nav (A), hero dashboard for queue (B), grouped failures (B),
// two-pane settings (B), rich preview for add (B), live-count tray (B).

function FinalShows() {
  return (
    <MacWindow title="Paragraphos" height={540} caption={
      "Final · library. Tabs up top, dense table (editorial, not spreadsheet-y). Queue banner shows inline when active. Status bar is the only place ETAs live so it never shouts."
    }>
      <div className="toolbar" style={{ padding: '6px 10px', gap: 2 }}>
        {['Shows','Queue','Failed','Settings'].map((t,i)=>(
          <div key={t} style={{
            padding: '5px 12px', borderRadius: 6, fontSize: 12.5,
            background: i===0 ? 'var(--accent-tint)' : 'transparent',
            color: i===0 ? 'var(--ink)' : 'var(--ink-3)',
            fontWeight: i===0 ? 600 : 400,
          }}>{t}</div>
        ))}
        <div className="grow"/>
        <div className="mono tiny muted" style={{marginRight:8}}>⌘R  check</div>
      </div>

      <div style={{ padding: 18, flex: 1, display:'flex', flexDirection:'column', gap: 12, overflow:'hidden' }}>
        <div className="row" style={{gap: 18, alignItems:'baseline'}}>
          <div>
            <div style={{fontSize:11, color:'var(--ink-3)', textTransform:'uppercase', letterSpacing:0.6, fontWeight:600}}>Library</div>
            <div className="row" style={{gap:16, marginTop:4}}>
              <Metric v="1 423" l="transcripts"/>
              <Metric v="1 842h" l="audio"/>
              <Metric v="11.8M"   l="words"/>
              <Metric v="23"      l="pending"/>
              <Metric v="4"       l="failed" danger/>
            </div>
          </div>
          <div className="grow"/>
          <button className="btn">Check feeds</button>
          <button className="btn">+ Add podcast</button>
          <button className="btn primary">Check now</button>
        </div>

        <div className="sk-box" style={{
          padding: '8px 12px',
          display:'flex', alignItems:'center', gap:12,
          borderColor:'var(--accent)',
          background:'var(--accent-tint)'
        }}>
          <Pill kind="running">running</Pill>
          <b className="mono">3/12</b>
          <div style={{width:180}}><Progress pct={25}/></div>
          <span className="tiny muted">odd-lots · The weird cargo-ship market…</span>
          <div className="grow"/>
          <button className="btn ghost">Pause</button>
          <button className="btn ghost">Stop</button>
        </div>

        <div style={{flex:1, overflow:'auto', border:'1px solid var(--line-soft)', borderRadius:8}}>
          <table className="wf-table">
            <thead>
              <tr>
                <th style={{width:36}}></th>
                <th>Show</th>
                <th style={{width:180}}>Progress</th>
                <th style={{width:70, textAlign:'right'}}>Pending</th>
                <th style={{width:80}}>Feed</th>
              </tr>
            </thead>
            <tbody>
              {SHOWS.map(s=>(
                <tr key={s.slug}>
                  <td>{s.on ? <span style={{color:'var(--accent)'}}>●</span> : <span className="dim">○</span>}</td>
                  <td>
                    <div style={{fontWeight:500}}>{s.title}</div>
                    <div className="mono tiny muted">{s.slug}</div>
                  </td>
                  <td>
                    <div className="row" style={{gap:8}}>
                      <div style={{flex:1}}><Progress pct={Math.round(s.done/s.total*100)}/></div>
                      <span className="mono tiny muted" style={{whiteSpace:'nowrap', width: 66, textAlign:'right'}}>{s.done}/{s.total}</span>
                    </div>
                  </td>
                  <td className="mono tiny" style={{textAlign:'right'}}>{s.pend}</td>
                  <td>{s.feed==='ok' ? <Pill kind="ok">ok</Pill> : <Pill kind="fail">stale</Pill>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <StatusBar visible={true}/>
    </MacWindow>
  );
}

function Metric({ v, l, danger }) {
  return (
    <div>
      <div className="mono" style={{fontSize:16, fontWeight:600, color: danger? 'var(--danger)': 'var(--ink)'}}>{v}</div>
      <div className="tiny muted" style={{fontSize: 11}}>{l}</div>
    </div>
  );
}

function FinalQueue() {
  const rows = [
    { show: 'a16z', title: "What's next for on-device ML", state: 'downloading' },
    { show: 'macro-musings', title: 'Nominal GDP targeting revisited', state: 'pending' },
    { show: 'the-property-pod', title: 'Yields in mid-tier German cities', state: 'pending' },
    { show: 'odd-lots', title: 'Why copper prices are where they are', state: 'pending' },
    { show: 'a16z', title: 'Climate tech, year 3', state: 'pending' },
  ];
  return (
    <MacWindow title="Paragraphos" height={540} caption={
      "Final · queue. Hero dashboard from B — started / elapsed / per-ep / finish as 4 equal stats. No ring gimmick; linear bar reads faster."
    }>
      <div className="toolbar" style={{ padding: '6px 10px', gap: 2 }}>
        {['Shows','Queue','Failed','Settings'].map((t,i)=>(
          <div key={t} style={{
            padding: '5px 12px', borderRadius: 6, fontSize: 12.5,
            background: i===1 ? 'var(--accent-tint)' : 'transparent',
            color: i===1 ? 'var(--ink)' : 'var(--ink-3)',
            fontWeight: i===1 ? 600 : 400,
          }}>{t}</div>
        ))}
      </div>
      <div style={{padding:18, flex:1, display:'flex', flexDirection:'column', gap:14, overflow:'hidden'}}>
        <div style={{border:'1px solid var(--line-soft)', borderRadius:10, padding:16}}>
          <div className="row" style={{gap:10, marginBottom: 10}}>
            <Pill kind="running">running</Pill>
            <b style={{fontSize:14}}>odd-lots — The weird cargo-ship market right now</b>
            <div className="grow"/>
            <button className="btn">Pause</button>
            <button className="btn">Stop</button>
          </div>
          <div className="row" style={{gap:10}}>
            <b className="mono" style={{fontSize:15}}>3 / 12</b>
            <div className="grow"><Progress pct={25}/></div>
            <span className="mono tiny muted">25%</span>
          </div>
          <div style={{display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:18, marginTop: 14}}>
            <Stat label="started" value="09:14" sub="Mo, 20.04"/>
            <Stat label="elapsed" value="18m 02s"/>
            <Stat label="per ep." value="4m 31s" sub="(est. 5m 40s)"/>
            <Stat label="finish ≈" value="10:24" sub="in 52m"/>
          </div>
        </div>
        <div style={{flex:1, overflow:'auto', border:'1px solid var(--line-soft)', borderRadius:8}}>
          <table className="wf-table">
            <thead><tr>
              <th>Show</th><th>Title</th><th style={{width:120}}>Status</th>
            </tr></thead>
            <tbody>
              {rows.map((r,i)=>(
                <tr key={i}>
                  <td className="mono tiny">{r.show}</td>
                  <td>{r.title}</td>
                  <td>
                    {r.state==='downloading' && <Pill kind="running">downloading</Pill>}
                    {r.state==='pending' && <Pill>pending</Pill>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <StatusBar visible={true}/>
    </MacWindow>
  );
}

function FinalFailed() {
  const groups = [
    { r: 'model hash mismatch', n: 1, hint: 'run: paragraphos verify-model' },
    { r: 'whisper: ggml_new_tensor', n: 1, hint: 'reduce --parallel to 1' },
    { r: 'mp3 > 2GB cap', n: 1, hint: 'feed includes videos? raise cap in settings' },
    { r: 'ssrf-guard: private IP', n: 1, hint: 'feed points at LAN; skipped by design' },
  ];
  return (
    <MacWindow title="Paragraphos" height={540} caption={
      "Final · failed. Grouped by cause (B). Each class has a single suggested remedy + batch-retry."
    }>
      <div className="toolbar" style={{ padding: '6px 10px', gap: 2 }}>
        {['Shows','Queue','Failed','Settings'].map((t,i)=>(
          <div key={t} style={{
            padding: '5px 12px', borderRadius: 6, fontSize: 12.5,
            background: i===2 ? 'var(--accent-tint)' : 'transparent',
            color: i===2 ? 'var(--ink)' : 'var(--ink-3)',
            fontWeight: i===2 ? 600 : 400,
          }}>{t}</div>
        ))}
      </div>
      <div style={{padding: 18, flex:1, overflow:'auto', display:'flex', flexDirection:'column', gap:10}}>
        <div className="row" style={{gap:10}}>
          <b>4 failed</b>
          <span className="tiny muted">in 4 classes</span>
          <div className="grow"/>
          <button className="btn ghost">Retry all</button>
        </div>
        {groups.map((g,i)=>(
          <div key={i} className="card" style={{padding:12}}>
            <div className="row">
              <div style={{width:6, height: 30, background:'var(--danger)', borderRadius: 3}}/>
              <div className="grow" style={{marginLeft: 4}}>
                <b className="mono" style={{fontSize:13}}>{g.r}</b>
                <div className="tiny muted" style={{marginTop:2}}>→ {g.hint}</div>
              </div>
              <span className="mono tiny muted">×{g.n}</span>
              <button className="btn ghost">Open log</button>
              <button className="btn">Retry class</button>
            </div>
          </div>
        ))}
      </div>
      <StatusBar visible={true}/>
    </MacWindow>
  );
}

function FinalSettings() {
  const groups = ['Library','Schedule','Engine','Storage','Notifications','Automation'];
  return (
    <MacWindow title="Paragraphos" height={540} caption={
      "Final · settings. Two-pane (B). Auto-saves; save indicator in toolbar."
    }>
      <div className="toolbar" style={{ padding: '6px 10px', gap: 2 }}>
        {['Shows','Queue','Failed','Settings'].map((t,i)=>(
          <div key={t} style={{
            padding: '5px 12px', borderRadius: 6, fontSize: 12.5,
            background: i===3 ? 'var(--accent-tint)' : 'transparent',
            color: i===3 ? 'var(--ink)' : 'var(--ink-3)',
            fontWeight: i===3 ? 600 : 400,
          }}>{t}</div>
        ))}
        <div className="grow"/>
        <span className="tiny" style={{color:'var(--ok)'}}>✓ saved 09:14:22</span>
      </div>
      <div style={{display:'flex', flex:1, overflow:'hidden'}}>
        <div style={{width: 170, borderRight:'1px solid var(--line-soft)', padding:'12px 8px', background: '#faf9f5'}}>
          {groups.map((g,i)=>(
            <div key={g} style={{padding:'7px 12px', borderRadius:6, fontSize:12.5, fontWeight: i===2?600:500, color: i===2?'var(--ink)':'var(--ink-3)',
              background: i===2 ? 'var(--accent-tint)':'transparent' }}>{g}</div>
          ))}
        </div>
        <div style={{flex:1, padding:20, overflow:'auto'}}>
          <div style={{fontSize: 16, fontWeight:600, marginBottom:4}}>Transcription engine</div>
          <div className="tiny muted" style={{marginBottom:18}}>All transcription runs locally via whisper.cpp.</div>
          <div style={{display:'grid', gridTemplateColumns:'180px 1fr', gap:'14px 18px', alignItems:'center'}}>
            <div className="tiny" style={{color:'var(--ink-2)', fontWeight:500}}>Whisper model</div>
            <div className="row" style={{gap:8}}>
              <div className="sk-box" style={{padding:'5px 10px', minWidth:220, fontSize:12}}>large-v3-turbo ▾</div>
              <Pill kind="ok">installed</Pill>
            </div>
            <div className="tiny" style={{color:'var(--ink-2)', fontWeight:500}}>Parallel workers</div>
            <div className="row" style={{gap:8}}>
              <div className="sk-box" style={{padding:'5px 10px', width:60, fontSize:12}}>2</div>
              <span className="tiny muted">recommended 2 (16 GB RAM, 8 perf cores)</span>
            </div>
            <div className="tiny" style={{color:'var(--ink-2)', fontWeight:500}}>Bandwidth limit</div>
            <div className="sk-box" style={{padding:'5px 10px', width:120, fontSize:12}}>0 Mbps (∞)</div>
          </div>
        </div>
      </div>
      <StatusBar visible={true}/>
    </MacWindow>
  );
}

function FinalPage() {
  return (
    <div className="page">
      <div className="page-head">
        <h1>Final direction · picked patterns</h1>
        <div className="sub">
          Tabs up top (A) · queue as a hero dashboard (B) · failures grouped by cause (B) · settings two-pane (B) · add-podcast with rich preview (B) · tray with live count (B).
          Toggle <b>Sketchy</b> off in the Tweaks panel to see this clean, or on to see how the same layouts feel lo-fi.
        </div>
      </div>
      <div className="variation-row" style={{gridTemplateColumns: '1fr 1fr'}}>
        <div><VariationLabel letter="1" name="Shows"    note="home"/><FinalShows/></div>
        <div><VariationLabel letter="2" name="Queue"    note="hero"/><FinalQueue/></div>
        <div><VariationLabel letter="3" name="Failed"   note="grouped"/><FinalFailed/></div>
        <div><VariationLabel letter="4" name="Settings" note="two-pane"/><FinalSettings/></div>
      </div>
    </div>
  );
}

Object.assign(window, { FinalPage });
