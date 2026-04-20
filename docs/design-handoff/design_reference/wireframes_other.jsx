// Failed, Settings, First-run, Add Podcast, Show Details, Tray menu

// ===== Failed tab =====
const FAILED = [
  { show: 'a16z', title: 'Climate tech, year 3', reason: 'model hash mismatch', attempts: 2, lastTry: '2026-04-20 09:02' },
  { show: 'odd-lots', title: 'Lithium supply mystery (pt. 2)', reason: 'whisper: ggml_new_tensor', attempts: 4, lastTry: '2026-04-20 08:44' },
  { show: 'the-property-pod', title: 'Office-to-resi conversions work?', reason: 'mp3 > 2GB cap', attempts: 1, lastTry: '2026-04-19 23:10' },
  { show: 'macro-musings', title: 'Term premium, revisited', reason: 'ssrf-guard: private IP', attempts: 1, lastTry: '2026-04-19 22:55' },
];

function FailedA({ showStatusbar }) {
  return (
    <MacWindow title="Paragraphos — Failed" height={440} caption="A · Flat table. Reason in-line, actions in a per-row menu.">
      <NavTabs active={2}/>
      <div style={{ padding: 14, flex: 1, overflow:'hidden', display:'flex', flexDirection:'column', gap: 10 }}>
        <div style={{ flex: 1, overflow: 'auto', border:'1.5px solid var(--line-soft)', borderRadius:6 }}>
          <table className="wf-table">
            <thead><tr>
              <th>Show</th><th>Episode</th><th>Reason</th><th style={{width:60}}>Tries</th><th style={{width:140}}>Last attempt</th><th style={{width:28}}></th>
            </tr></thead>
            <tbody>
              {FAILED.map((r,i)=>(
                <tr key={i}>
                  <td className="mono tiny">{r.show}</td>
                  <td>{r.title}</td>
                  <td><span className="tiny" style={{color:'var(--danger)'}}>{r.reason}</span></td>
                  <td className="mono tiny">{r.attempts}</td>
                  <td className="mono tiny muted">{r.lastTry}</td>
                  <td className="muted">⋯</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="row" style={{gap:6}}>
          <button className="btn">Retry selected</button>
          <button className="btn">Mark resolved</button>
          <div className="grow"/>
          <button className="btn ghost">Export .log</button>
        </div>
      </div>
      <StatusBar visible={showStatusbar}/>
    </MacWindow>
  );
}

function FailedB({ showStatusbar }) {
  return (
    <MacWindow title="Paragraphos — Failed" height={440} caption="B · Grouped by reason. Batch-retry the whole class at once.">
      <NavTabs active={2}/>
      <div style={{ padding: 14, flex: 1, overflow: 'auto', display:'flex', flexDirection:'column', gap: 10 }}>
        {[
          { r: 'model hash mismatch', n: 1, hint: 'run: paragraphos verify-model' },
          { r: 'whisper: ggml_new_tensor', n: 1, hint: 'reduce --parallel to 1' },
          { r: 'mp3 > 2GB cap', n: 1, hint: 'feed includes videos? raise cap in settings' },
          { r: 'ssrf-guard: private IP', n: 1, hint: 'feed points at LAN; skipped by design' },
        ].map((g,i)=>(
          <div key={i} className="card" style={{padding: 10}}>
            <div className="row">
              <b>{g.r}</b>
              <span className="mono tiny muted">× {g.n}</span>
              <div className="grow"/>
              <button className="btn ghost">Retry class</button>
              <button className="btn ghost">Dismiss</button>
            </div>
            <div className="tiny muted" style={{marginTop:4}}>→ {g.hint}</div>
          </div>
        ))}
      </div>
      <StatusBar visible={showStatusbar}/>
    </MacWindow>
  );
}

function FailedC({ showStatusbar }) {
  return (
    <MacWindow title="Paragraphos — Failed" height={440} caption="C · Split view. List on left, full log + resolve-action on right.">
      <NavTabs active={2}/>
      <div style={{ display:'flex', flex: 1, overflow: 'hidden' }}>
        <div style={{ width: 240, borderRight: '1.5px solid var(--line-soft)', overflow:'auto' }}>
          {FAILED.map((r,i)=>(
            <div key={i} style={{padding: '8px 10px', borderBottom:'1px solid var(--line-soft)', background: i===1? 'var(--accent-tint)':'transparent'}}>
              <div style={{fontWeight:500, fontSize: 13}}>{r.title}</div>
              <div className="mono tiny muted">{r.show} · {r.attempts}×</div>
              <div className="tiny" style={{color:'var(--danger)', marginTop:2}}>{r.reason}</div>
            </div>
          ))}
        </div>
        <div style={{ flex: 1, padding: 12, display:'flex', flexDirection:'column', gap: 8 }}>
          <div className="row">
            <b className="tiny">odd-lots — Lithium supply mystery (pt. 2)</b>
            <div className="grow"/>
            <button className="btn">Retry</button>
            <button className="btn">Skip</button>
          </div>
          <div className="log-dock" style={{flex:1, maxHeight:'none'}}>
            <div><span className="ts">09:02:14</span> <span className="lvl-info">INFO</span>  downloading mp3 …</div>
            <div><span className="ts">09:02:31</span> <span className="lvl-info">INFO</span>  78 MB/140 MB</div>
            <div><span className="ts">09:03:02</span> <span className="lvl-info">INFO</span>  transcribe start — model=large-v3-turbo</div>
            <div><span className="ts">09:03:44</span> <span className="lvl-warn">WARN</span>  ggml_new_tensor: alloc failed</div>
            <div><span className="ts">09:03:44</span> <span className="lvl-warn">WARN</span>  retry 3 of 4 …</div>
            <div style={{color:'#e06070'}}>09:04:58 ERROR whisper: tensor alloc failed, giving up</div>
          </div>
        </div>
      </div>
      <StatusBar visible={showStatusbar}/>
    </MacWindow>
  );
}

function FailedPage({ showStatusbar }) {
  return (
    <div className="page">
      <div className="page-head">
        <h1>Failed · episodes</h1>
        <div className="sub">How do we surface errors without terrifying users? Flat list vs. grouped-by-cause vs. detail view with logs.</div>
      </div>
      <div className="variation-row">
        <div><VariationLabel letter="A" name="Flat table" note="like today"/><FailedA showStatusbar={showStatusbar}/></div>
        <div><VariationLabel letter="B" name="Grouped by cause" note="batch-resolve"/><FailedB showStatusbar={showStatusbar}/></div>
        <div><VariationLabel letter="C" name="Split + log" note="diagnostic"/><FailedC showStatusbar={showStatusbar}/></div>
      </div>
    </div>
  );
}

// ===== Nav shell tabs (reused) =====
function NavTabs({ active }) {
  return (
    <div className="toolbar" style={{ padding: '6px 10px', gap: 4 }}>
      {['Shows','Queue','Failed','Settings'].map((t,i)=>(
        <div key={t} style={{
          padding: '4px 10px', borderRadius: 5, fontSize: 13,
          background: i===active ? 'var(--accent-tint)' : 'transparent',
          color: i===active ? 'var(--ink)' : 'var(--ink-3)',
          fontWeight: i===active ? 600 : 400,
        }}>{t}</div>
      ))}
    </div>
  );
}

// ===== Settings =====
const SETTINGS_GROUPS_A = [
  { name: 'Library & output', fields: [
    { l: 'Output root', v: '~/wiki/raw/podcasts', hint: 'markdown transcripts land here, one folder per show' },
    { l: 'Obsidian vault', v: '~/wiki', hint: 'auto-fills vault name from folder (“wiki”)' },
  ]},
  { name: 'Schedule & monitoring', fields: [
    { l: 'Daily check time', v: '09:00', hint: 'runs in the background — Mac must be awake' },
    { l: 'Catch-up missed runs', v: '☑ on', hint: 'recommended — runs immediately on wake if a check was missed' },
  ]},
  { name: 'Notifications', fields: [
    { l: 'Notify on success', v: '☑ on', hint: 'if silent: re-enable in macOS → Notifications', kind: 'info' },
  ]},
  { name: 'Transcription engine', fields: [
    { l: 'Whisper model', v: 'large-v3-turbo', status: '● installed', hint: 'best accuracy/speed balance on Apple Silicon — recommended', kind: 'good' },
    { l: 'Parallel workers', v: '2', hint: 'recommended: 2  (16 GB RAM, 8 perf cores detected)', kind: 'good' },
    { l: 'Bandwidth limit', v: '0 Mbps', hint: '0 = unlimited. Try 20 Mbps if shared Wi-Fi starts hitching', kind: 'info' },
  ]},
  { name: 'Storage & retention', fields: [
    { l: 'MP3 retention', v: '30 days', hint: 'transcripts are kept forever — only the audio is purged' },
    { l: 'Delete MP3 after transcribe', v: '☐ off', hint: 'turn on to save ~40 GB/yr if you never re-play audio', kind: 'info' },
    { l: 'Log retention', v: '14 days', hint: 'enough to debug any failed run' },
  ]},
];

function SettingsA({ showStatusbar }) {
  return (
    <MacWindow title="Paragraphos — Settings" height={520} caption="A · In-tab, single long scroll. Auto-saves. Today's shape.">
      <NavTabs active={3}/>
      <div style={{ flex: 1, padding: 14, overflow: 'auto' }}>
        {SETTINGS_GROUPS_A.map((g, gi)=>(
          <div key={gi} style={{marginBottom: 18}}>
            <div style={{borderBottom:'1px solid var(--line-soft)', paddingBottom:4, marginBottom:8, color:'var(--ink-3)', fontSize:11, textTransform:'uppercase', letterSpacing:0.5, fontWeight:600}}>{g.name}</div>
            <div style={{display:'grid', gridTemplateColumns: '150px 1fr', gap: '8px 12px'}}>
              {g.fields.map((f, fi) => <Field key={fi} {...f}/>)}
            </div>
          </div>
        ))}
      </div>
      <StatusBar visible={showStatusbar}/>
    </MacWindow>
  );
}

function Field({ l, label, v, val, status, hint, kind = 'muted' }) {
  const lab = l ?? label;
  const value = v ?? val;
  const hintColor = {
    good: 'var(--accent)',
    info: 'var(--ink-3)',
    muted: 'var(--ink-3)',
  }[kind];
  const hintPrefix = { good: '✓', info: 'ⓘ', muted: '↳' }[kind];
  return (
    <>
      <div className="muted tiny" style={{paddingTop: 6, textAlign:'right'}}>{lab}</div>
      <div>
        <div className="row" style={{gap: 8, alignItems: 'center'}}>
          <div className="sk-box" style={{padding:'5px 9px', fontSize: 12, flex: 1}}>{value}</div>
          {status && <span className="tiny" style={{color:'var(--accent)'}}>{status}</span>}
        </div>
        {hint && (
          <div className="tiny" style={{marginTop: 3, color: hintColor, fontStyle: kind === 'good' ? 'normal' : 'italic', lineHeight: 1.35}}>
            <span style={{opacity: 0.7, marginRight: 4}}>{hintPrefix}</span>{hint}
          </div>
        )}
      </div>
    </>
  );
}

function SettingsB({ showStatusbar }) {
  const groups = ['Library','Schedule','Engine','Storage','Notifications','Automation'];
  return (
    <MacWindow title="Paragraphos — Settings" height={520} caption="B · Two-pane. Sections on left, form on right. Easier to scan & jump.">
      <NavTabs active={3}/>
      <div style={{display:'flex', flex:1, overflow:'hidden'}}>
        <div style={{width: 150, borderRight:'1.5px solid var(--line-soft)', padding:'10px 6px'}}>
          {groups.map((g,i)=>(
            <div key={g} style={{padding:'6px 10px', borderRadius:5, fontSize:12, fontWeight: i===2?600:400,
              background: i===2 ? 'var(--accent-tint)':'transparent' }}>{g}</div>
          ))}
        </div>
        <div style={{flex:1, padding: 16, overflow:'auto'}}>
          <div style={{fontWeight:600, marginBottom:10, fontSize: 14}}>Transcription engine</div>
          <div style={{display:'grid', gridTemplateColumns:'150px 1fr', gap:'10px 14px'}}>
            <Field l="Whisper model" v="large-v3-turbo" status="● installed"
                   hint="best accuracy/speed on Apple Silicon — recommended" kind="good"/>
            <Field l="Parallel workers" v="2"
                   hint="recommended: 2  (16 GB RAM, 8 perf cores detected)" kind="good"/>
            <Field l="Bandwidth limit" v="0 Mbps (∞)"
                   hint="0 = unlimited. Cap at ~20 Mbps if you share Wi-Fi during checks" kind="info"/>
          </div>
          <Callout>parallel &gt; 2 uses ~11 GB RAM peak — watch thermals</Callout>
        </div>
      </div>
      <StatusBar visible={showStatusbar}/>
    </MacWindow>
  );
}

function SettingsC({ showStatusbar }) {
  return (
    <MacWindow title="Paragraphos" height={520} caption="C · Modal sheet over the library. Opens on ⌘, — less wall of settings.">
      <NavTabs active={0}/>
      <div style={{ padding: 14, flex:1, position:'relative' }}>
        {/* faded library behind */}
        <div style={{opacity:0.35}}>
          <table className="wf-table">
            <thead><tr><th>Title</th><th>Progress</th></tr></thead>
            <tbody>
              {SHOWS.slice(0,4).map(s=>(
                <tr key={s.slug}><td>{s.title}</td><td><Progress pct={Math.round(s.done/s.total*100)}/></td></tr>
              ))}
            </tbody>
          </table>
        </div>
        {/* sheet */}
        <div style={{
          position:'absolute', left:'50%', top:'8%',
          transform:'translateX(-50%)', width: '84%',
        }}>
          <div className="dlg">
            <div className="dlg-title" style={{display:'flex', alignItems:'center'}}>
              <span>Settings</span>
              <div className="grow"/>
              <span className="tiny muted">✓ saved</span>
            </div>
            <div style={{padding:14}}>
              <div style={{
                padding: '6px 10px', marginBottom: 10, borderRadius: 5,
                background: 'var(--accent-tint)', color: 'var(--accent)',
                fontSize: 11, fontStyle: 'italic',
              }}>
                ⓘ Hover any field for a recommendation — e.g. “parallel: 2 (16 GB RAM, 8 perf cores)”
              </div>
              <div style={{display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:8, fontSize: 12}}>
                <Field label="Output" val="~/wiki/raw/podcasts"/>
                <Field label="Daily check" val="09:00"/>
                <Field label="Model" val="large-v3-turbo" status="✓"/>
                <Field label="Parallel" val="2" status="rec"/>
                <Field label="Bandwidth" val="0 Mbps"/>
                <Field label="MP3 retention" val="30 days"/>
              </div>
            </div>
          </div>
        </div>
      </div>
      <StatusBar visible={showStatusbar}/>
    </MacWindow>
  );
}

function SettingsPage({ showStatusbar }) {
  return (
    <div className="page">
      <div className="page-head">
        <h1>Settings</h1>
        <div className="sub">Where do settings live — tab, two-pane, or modal sheet?</div>
      </div>
      <div className="variation-row">
        <div><VariationLabel letter="A" name="In-tab scroll" note="today"/><SettingsA showStatusbar={showStatusbar}/></div>
        <div><VariationLabel letter="B" name="Two-pane" note="sidebar + form"/><SettingsB showStatusbar={showStatusbar}/></div>
        <div><VariationLabel letter="C" name="Modal sheet" note="⌘, overlay"/><SettingsC showStatusbar={showStatusbar}/></div>
      </div>
    </div>
  );
}

// ===== First-run wizard =====
function Wiz({ variant }) {
  const steps = [
    { label: 'Homebrew', status: 'ok' },
    { label: 'whisper-cpp', status: 'ok' },
    { label: 'ffmpeg', status: 'ok' },
    { label: 'large-v3-turbo (1.5 GB)', status: 'progress', pct: 62 },
  ];
  if (variant === 'A') {
    return (
      <div className="dlg" style={{width: 520}}>
        <div className="dlg-title">Paragraphos — First-run setup</div>
        <div style={{padding: 18}}>
          <h3 style={{margin:'0 0 4px'}}>Welcome to Paragraphos</h3>
          <p className="muted tiny" style={{marginTop:0}}>Everything runs locally. We need a few tools on your Mac before the first run.</p>
          <div className="stack">
            {steps.map((s,i)=>(
              <div key={i} className="row" style={{padding:'6px 0', borderBottom:'1px solid var(--line-soft)'}}>
                <div className="grow" style={{fontWeight:500, fontSize:13}}>{s.label}</div>
                {s.status==='ok' && <Pill kind="ok">✓ installed</Pill>}
                {s.status==='progress' && (
                  <>
                    <div style={{width:140}}><Progress pct={s.pct}/></div>
                    <span className="mono tiny">{s.pct}%</span>
                  </>
                )}
              </div>
            ))}
          </div>
          <div className="row" style={{marginTop: 16, justifyContent:'flex-end'}}>
            <button className="btn ghost">Cancel</button>
            <button className="btn primary" disabled>Continue to Paragraphos</button>
          </div>
        </div>
      </div>
    );
  }
  if (variant === 'B') {
    return (
      <div className="dlg" style={{width: 520}}>
        <div className="dlg-title">Paragraphos — setup · step 4 of 4</div>
        <div style={{padding:18}}>
          <div className="tiny muted">Step 4</div>
          <h3 style={{margin:'2px 0 6px'}}>Downloading whisper model</h3>
          <p className="muted tiny" style={{marginTop:0}}>large-v3-turbo is ~1.5 GB. We verify the SHA-256 before using it.</p>
          <div style={{margin: '14px 0'}}>
            <Progress pct={62}/>
            <div className="row" style={{marginTop:4}}>
              <span className="mono tiny">943 MB of 1.52 GB</span>
              <span className="mono tiny muted grow" style={{textAlign:'right'}}>28 MB/s · 21s</span>
            </div>
          </div>
          <div className="stepper row" style={{gap:6, marginTop: 12}}>
            {['Brew','whisper-cpp','ffmpeg','Model'].map((s,i)=>(
              <span key={s} style={{flex:1, height:4, background: i<3 ? 'var(--accent)' : i===3 ? 'var(--accent-tint)' : 'var(--line-soft)'}}/>
            ))}
          </div>
          <div className="row" style={{marginTop: 16, justifyContent:'flex-end'}}>
            <button className="btn ghost">Cancel</button>
            <button className="btn primary" disabled>Next</button>
          </div>
        </div>
      </div>
    );
  }
  // C — checklist with ASCII diagram of the local pipeline
  return (
    <div className="dlg" style={{width: 560}}>
      <div className="dlg-title">Paragraphos — local-only by design</div>
      <div style={{padding:18}}>
        <div className="mono tiny" style={{whiteSpace:'pre', background:'#1a1a1a', color:'#c8c3b4', padding: 10, borderRadius: 6, lineHeight: 1.6}}>
{` RSS ──▶ [download] ──▶ [whisper.cpp] ──▶ .md  ──▶ ~/wiki
  ✓           ✓              ↓ 62%            0
                           (local)`}
        </div>
        <p className="muted tiny" style={{marginTop:10}}>Nothing leaves your machine. No API keys, no cloud ASR, no telemetry.</p>
        <div className="row" style={{marginTop:14, justifyContent:'flex-end'}}>
          <button className="btn ghost">Cancel</button>
          <button className="btn primary" disabled>Finish when ready</button>
        </div>
      </div>
    </div>
  );
}

function WizardPage() {
  return (
    <div className="page">
      <div className="page-head">
        <h1>First-run wizard</h1>
        <div className="sub">Everything is local. Show the pipeline — don't bury it.</div>
      </div>
      <div className="variation-row">
        <div><VariationLabel letter="A" name="Checklist" note="today"/><div style={{display:'flex', justifyContent:'center'}}><Wiz variant="A"/></div><div className="wf-caption" style={{marginTop:10}}>A · All 4 deps in one list. Simplest.</div></div>
        <div><VariationLabel letter="B" name="Stepper" note="one step at a time"/><div style={{display:'flex', justifyContent:'center'}}><Wiz variant="B"/></div><div className="wf-caption" style={{marginTop:10}}>B · One step per screen. Slower but less overwhelming.</div></div>
        <div><VariationLabel letter="C" name="Manifesto" note="local-only pitch"/><div style={{display:'flex', justifyContent:'center'}}><Wiz variant="C"/></div><div className="wf-caption" style={{marginTop:10}}>C · Leads with "nothing leaves your machine" — positions the setup as a feature.</div></div>
      </div>
    </div>
  );
}

// ===== Add Podcast dialog =====
function AddA() {
  return (
    <div className="dlg" style={{width: 540}}>
      <div className="dlg-title">Add podcast</div>
      <div style={{padding:16}}>
        <div className="tiny muted">Name or URL</div>
        <div className="sk-box" style={{marginTop:4, padding:'6px 10px'}}>odd lots</div>
        <div className="row" style={{marginTop:6, justifyContent:'flex-end'}}>
          <button className="btn primary">Search</button>
        </div>
        <div style={{border:'1.5px solid var(--line-soft)', borderRadius:6, marginTop:10, maxHeight: 140, overflow:'auto'}}>
          {['Odd Lots — Bloomberg','Odd Lots Abroad — Bloomberg','The Odd Lot Podcast — J. Ho'].map((x,i)=>(
            <div key={i} style={{padding:'6px 10px', borderBottom:'1px solid var(--line-soft)', background: i===0?'var(--accent-tint)':'transparent'}}>{x}</div>
          ))}
        </div>
        <div style={{display:'grid', gridTemplateColumns:'110px 1fr', gap:'6px 10px', marginTop: 12, fontSize: 12}}>
          <div className="muted" style={{alignSelf:'center'}}>Slug</div><div className="sk-box" style={{padding:'4px 8px'}}>odd-lots</div>
          <div className="muted" style={{alignSelf:'center'}}>Title</div><div className="sk-box" style={{padding:'4px 8px'}}>Odd Lots</div>
          <div className="muted" style={{alignSelf:'center'}}>RSS</div><div className="sk-box mono tiny" style={{padding:'4px 8px'}}>https://feeds.bloomberg.fm/BBN4209091844</div>
          <div className="muted" style={{alignSelf:'center'}}>Backlog</div><div className="sk-box" style={{padding:'4px 8px'}}>Only new from now ▾</div>
          <div className="muted" style={{alignSelf:'flex-start', paddingTop:4}}>Whisper prompt</div>
          <div className="sk-box tiny" style={{padding:'6px 8px', minHeight:54, lineHeight:1.4}}>This is Odd Lots, a podcast about money, markets & odd corners of finance. Hosts: Joe Weisenthal, Tracy Alloway. Bloomberg.</div>
        </div>
        <div className="row" style={{marginTop:14, justifyContent:'flex-end'}}>
          <button className="btn ghost">Cancel</button>
          <button className="btn primary">Save</button>
        </div>
      </div>
    </div>
  );
}

function AddB() {
  return (
    <div className="dlg" style={{width: 540}}>
      <div className="dlg-title">Add podcast · preview</div>
      <div style={{padding:16}}>
        <div className="row">
          <div className="placeholder" style={{width:72, height:72, padding:0, display:'flex', alignItems:'center', justifyContent:'center'}}>artwork</div>
          <div className="grow" style={{marginLeft:12}}>
            <div style={{fontWeight:600, fontSize:15}}>Odd Lots</div>
            <div className="tiny muted">Bloomberg · Joe Weisenthal, Tracy Alloway</div>
            <div className="tiny mono muted" style={{marginTop:4}}>412 episodes · latest 2026-04-19</div>
          </div>
        </div>
        <Callout>We auto-generated a whisper prompt from the last 20 episode titles — edit if needed.</Callout>
        <div style={{border:'1.5px solid var(--line-soft)', borderRadius:6, padding:8, marginTop:10, fontSize:12}}>
          <div className="muted tiny" style={{marginBottom:4}}>Whisper prompt</div>
          <div>This is Odd Lots. Money, markets, odd corners of finance. Hosts: Joe Weisenthal, Tracy Alloway. Bloomberg.</div>
        </div>
        <div className="row" style={{marginTop: 10, gap: 14}}>
          <Seg label="Backlog" options={['All','Only new','Last 20','Last 50']} active={1}/>
        </div>
        <div className="row" style={{marginTop:14, justifyContent:'flex-end'}}>
          <button className="btn ghost">Cancel</button>
          <button className="btn primary">Save & start</button>
        </div>
      </div>
    </div>
  );
}

function Seg({ label, options, active }) {
  return (
    <div>
      <div className="muted tiny" style={{marginBottom:4}}>{label}</div>
      <div style={{display:'inline-flex', border:'1.5px solid var(--line-soft)', borderRadius:6, overflow:'hidden'}}>
        {options.map((o,i)=>(
          <div key={o} style={{padding:'4px 10px', fontSize:12, background: i===active? 'var(--accent)':'transparent', color: i===active?'white':'var(--ink-2)', borderRight: i<options.length-1?'1px solid var(--line-soft)':'none'}}>{o}</div>
        ))}
      </div>
    </div>
  );
}

function AddC() {
  return (
    <div className="dlg" style={{width: 540}}>
      <div className="dlg-title">Paste a feed URL or podcast link</div>
      <div style={{padding:16}}>
        <div className="sk-box" style={{padding:'10px 12px', fontSize:13}} className="mono">https://podcasts.apple.com/us/podcast/odd-lots</div>
        <Callout>We'll follow the Apple link → find the RSS → build a preview</Callout>
        <div style={{marginTop:10, padding:10, border:'1.5px dashed var(--line-soft)', borderRadius:6}}>
          <div className="tiny muted">Auto-detected:</div>
          <div className="row" style={{marginTop:4}}>
            <div className="grow"><b className="tiny">Odd Lots</b><div className="mono tiny muted">412 eps · feeds.bloomberg.fm/BBN4209091844</div></div>
            <Pill kind="ok">feed ok</Pill>
          </div>
        </div>
        <div className="row" style={{marginTop:14, justifyContent:'flex-end'}}>
          <button className="btn ghost">Cancel</button>
          <button className="btn">Customise…</button>
          <button className="btn primary">Add</button>
        </div>
      </div>
    </div>
  );
}

function AddPage() {
  return (
    <div className="page">
      <div className="page-head">
        <h1>Add podcast</h1>
        <div className="sub">Search-heavy vs. preview-heavy vs. paste-and-go.</div>
      </div>
      <div className="variation-row">
        <div><VariationLabel letter="A" name="Search + form" note="today"/><div style={{display:'flex', justifyContent:'center'}}><AddA/></div></div>
        <div><VariationLabel letter="B" name="Rich preview" note="artwork, auto-prompt"/><div style={{display:'flex', justifyContent:'center'}}><AddB/></div></div>
        <div><VariationLabel letter="C" name="Paste URL, done" note="one-step"/><div style={{display:'flex', justifyContent:'center'}}><AddC/></div></div>
      </div>
    </div>
  );
}

// ===== Show details dialog =====
function DetailsA() {
  return (
    <div className="dlg" style={{width: 620, minHeight: 440}}>
      <div className="dlg-title">Odd Lots · details</div>
      <div style={{padding:16}}>
        <div className="row" style={{marginBottom: 12}}>
          <div className="placeholder" style={{width:64, height:64, padding:0}}>art</div>
          <div className="grow" style={{marginLeft:12}}>
            <div style={{fontWeight:600, fontSize:15}}>Odd Lots</div>
            <div className="tiny muted">odd-lots · 412 eps · 389 done · 23 pending</div>
            <div className="mono tiny muted">feeds.bloomberg.fm/BBN4209091844</div>
          </div>
          <Pill kind="ok">feed ok</Pill>
        </div>
        <div style={{display:'grid', gridTemplateColumns:'120px 1fr', gap:'6px 10px', fontSize: 12}}>
          <div className="muted" style={{alignSelf:'center'}}>Enabled</div><div>●</div>
          <div className="muted" style={{alignSelf:'flex-start', paddingTop:4}}>Whisper prompt</div>
          <div className="sk-box tiny" style={{padding:'6px 8px', minHeight:40}}>Money, markets, odd corners of finance. Hosts: Joe Weisenthal, Tracy Alloway.</div>
        </div>
        <div style={{marginTop:12, fontWeight:600, fontSize:12}}>Recent episodes</div>
        <div style={{border:'1.5px solid var(--line-soft)', borderRadius:6, marginTop:4, maxHeight: 140, overflow:'auto'}}>
          {[
            ['2026-04-18','The weird cargo-ship market','done'],
            ['2026-04-15','Why copper prices are where they are','done'],
            ['2026-04-11','Hedge fund crowding, now with data','done'],
            ['2026-04-08','Lithium supply mystery (pt. 2)','failed'],
            ['2026-04-04','The term premium problem','pending'],
          ].map((r,i)=>(
            <div key={i} className="row" style={{padding:'5px 10px', borderBottom:'1px solid var(--line-soft)', fontSize:12}}>
              <span className="mono tiny muted" style={{width: 80}}>{r[0]}</span>
              <span className="grow">{r[1]}</span>
              <Pill kind={r[2]==='done'?'ok':r[2]==='failed'?'fail':'idle'}>{r[2]}</Pill>
            </div>
          ))}
        </div>
        <div className="row" style={{marginTop:14, justifyContent:'flex-end'}}>
          <button className="btn ghost">Remove</button>
          <button className="btn">Mark all stale</button>
          <button className="btn primary">Save</button>
        </div>
      </div>
    </div>
  );
}

// ===== Tray menu =====
function TrayA() {
  return (
    <div style={{position:'relative'}}>
      <div className="mac-window" style={{width: 360, minHeight:120, padding:0}}>
        <div className="mac-titlebar"><TRAFFIC/><div className="mac-title-text">menu bar</div><div style={{width:56}}/></div>
        <div style={{padding:'10px 14px', display:'flex', alignItems:'center', gap:10}}>
          <div style={{width:20, height:20, borderRadius:10, background:'#1a1a1a', color:'white', fontSize:11, display:'flex', alignItems:'center', justifyContent:'center', fontWeight:700}}>P</div>
          <span className="tiny muted">← click here</span>
          <div className="grow"/>
          <span className="mono tiny muted">🔋 ⏷ 9:14</span>
        </div>
      </div>
      <div style={{position:'absolute', top: 54, left: 30}}>
        <div className="tray-menu">
          <div className="item">Open <span className="mono tiny muted">⌘O</span></div>
          <div className="item">Check now <span className="mono tiny muted">⌘R</span></div>
          <div className="sep"/>
          <div className="item">Import OPML…</div>
          <div className="sep"/>
          <div className="item">Quit <span className="mono tiny muted">⌘Q</span></div>
        </div>
      </div>
    </div>
  );
}

function TrayB() {
  return (
    <div style={{position:'relative'}}>
      <div className="mac-window" style={{width: 360, minHeight:120, padding:0}}>
        <div className="mac-titlebar"><TRAFFIC/><div className="mac-title-text">menu bar</div><div style={{width:56}}/></div>
        <div style={{padding:'10px 14px', display:'flex', alignItems:'center', gap:10}}>
          <div style={{width:20, height:20, borderRadius:10, background:'#1a1a1a', color:'white', fontSize:10, display:'flex', alignItems:'center', justifyContent:'center', fontWeight:700}}>3/12</div>
          <span className="tiny muted">← live count in the icon</span>
        </div>
      </div>
      <div style={{position:'absolute', top: 54, left: 20}}>
        <div className="tray-menu" style={{minWidth:280}}>
          <div style={{padding:'6px 10px'}}>
            <div className="row">
              <Pill kind="running">running</Pill>
              <b className="mono tiny">3/12</b>
              <div className="grow"/>
              <span className="mono tiny muted">ETA 52m</span>
            </div>
            <div style={{marginTop:6}}><Progress pct={25}/></div>
            <div className="tiny muted" style={{marginTop:6}}>Now: odd-lots — The weird cargo-ship market…</div>
          </div>
          <div className="sep"/>
          <div className="item">Open window</div>
          <div className="item">Pause</div>
          <div className="item">Stop</div>
          <div className="sep"/>
          <div className="item">Import OPML…</div>
          <div className="item">Quit</div>
        </div>
      </div>
    </div>
  );
}

function TrayC() {
  return (
    <div style={{position:'relative'}}>
      <div className="mac-window" style={{width: 360, minHeight:120, padding:0}}>
        <div className="mac-titlebar"><TRAFFIC/><div className="mac-title-text">menu bar</div><div style={{width:56}}/></div>
        <div style={{padding:'10px 14px'}}>
          <span className="tiny muted">idle state — tiny P only</span>
        </div>
      </div>
      <div style={{position:'absolute', top: 54, left: 30}}>
        <div className="tray-menu" style={{minWidth: 260}}>
          <div style={{padding:'8px 10px'}}>
            <div className="tiny muted" style={{textTransform:'uppercase', letterSpacing:.6, fontSize:10}}>Last run</div>
            <div><b className="mono tiny">Mo, 20.04.2026 09:14</b></div>
            <div className="tiny muted">12 new · 0 failed · 54m</div>
          </div>
          <div className="sep"/>
          <div className="item">Open window</div>
          <div className="item">Check now</div>
          <div className="sep"/>
          <div className="item">Pause schedule</div>
          <div className="item">Quit</div>
        </div>
      </div>
    </div>
  );
}

function OtherScreensPage() {
  return (
    <div className="page">
      <div className="section-head"><h2>Add podcast dialog</h2><div className="line"/></div>
      <div className="variation-row">
        <div><VariationLabel letter="A" name="Search + form" note="today"/><div style={{display:'flex', justifyContent:'center'}}><AddA/></div></div>
        <div><VariationLabel letter="B" name="Rich preview" note="artwork, auto-prompt"/><div style={{display:'flex', justifyContent:'center'}}><AddB/></div></div>
        <div><VariationLabel letter="C" name="Paste URL" note="one-step"/><div style={{display:'flex', justifyContent:'center'}}><AddC/></div></div>
      </div>

      <div className="section-head"><h2>Show details</h2><div className="line"/></div>
      <div className="variation-row" style={{gridTemplateColumns: '1fr'}}>
        <div><VariationLabel letter="A" name="Full details sheet" note="one variant — this dialog has a single right answer"/>
          <div style={{display:'flex', justifyContent:'center'}}><DetailsA/></div>
        </div>
      </div>

      <div className="section-head"><h2>Menu-bar tray</h2><div className="line"/></div>
      <div className="variation-row">
        <div><VariationLabel letter="A" name="Classic" note="current"/><div style={{display:'flex', justifyContent:'center'}}><TrayA/></div>
          <div className="wf-caption" style={{marginTop: 10}}>A · Static 'P' icon, 4 menu items. Today's shape.</div>
        </div>
        <div><VariationLabel letter="B" name="Live count" note="icon shows 3/12"/><div style={{display:'flex', justifyContent:'center'}}><TrayB/></div>
          <div className="wf-caption" style={{marginTop: 10}}>B · Icon text updates live; menu includes the active progress bar so you don't have to open the window.</div>
        </div>
        <div><VariationLabel letter="C" name="Last-run summary" note="for off-hours"/><div style={{display:'flex', justifyContent:'center'}}><TrayC/></div>
          <div className="wf-caption" style={{marginTop: 10}}>C · Between runs shows the last run's stats. Pause-schedule is a first-class action.</div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { FailedPage, SettingsPage, WizardPage, AddPage, OtherScreensPage, DetailsA });
