// App shell — top nav, tweaks panel, routing.

const TABS = [
  { id: 'shows',    label: 'Shows',      comp: 'ShowsPage' },
  { id: 'queue',    label: 'Queue',      comp: 'QueuePage' },
  { id: 'failed',   label: 'Failed',     comp: 'FailedPage' },
  { id: 'settings', label: 'Settings',   comp: 'SettingsPage' },
  { id: 'wizard',   label: 'First-run',  comp: 'WizardPage' },
  { id: 'other',    label: 'Add / Details / Tray', comp: 'OtherScreensPage' },
  { id: 'final',    label: 'Final ★',    comp: 'FinalPage' },
];

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "sketchy": true,
  "showStatusbar": true,
  "accent": "ochre"
}/*EDITMODE-END*/;

const ACCENTS = {
  ochre: 'oklch(0.68 0.14 55)',
  clay:  'oklch(0.60 0.14 30)',
  moss:  'oklch(0.58 0.11 150)',
  indigo:'oklch(0.55 0.14 265)',
};

function App() {
  const [tab, setTab] = React.useState(() => {
    return localStorage.getItem('paragraphos-tab') || 'shows';
  });
  const [sketchy, setSketchy] = React.useState(TWEAK_DEFAULTS.sketchy);
  const [showStatusbar, setShowStatusbar] = React.useState(TWEAK_DEFAULTS.showStatusbar);
  const [accent, setAccent] = React.useState(TWEAK_DEFAULTS.accent);
  const [editMode, setEditMode] = React.useState(false);

  // persist tab
  React.useEffect(() => { localStorage.setItem('paragraphos-tab', tab); }, [tab]);

  // body class for sketchy vs clean
  React.useEffect(() => {
    document.body.classList.toggle('clean', !sketchy);
  }, [sketchy]);

  // accent color
  React.useEffect(() => {
    const c = ACCENTS[accent] || ACCENTS.ochre;
    document.documentElement.style.setProperty('--accent', c);
    // recompute tint
    const tint = c.replace(/\)$/, ' / 0.14)');
    document.documentElement.style.setProperty('--accent-tint', tint);
  }, [accent]);

  // Tweaks edit-mode wiring
  React.useEffect(() => {
    function onMsg(e) {
      if (e.data?.type === '__activate_edit_mode') setEditMode(true);
      if (e.data?.type === '__deactivate_edit_mode') setEditMode(false);
    }
    window.addEventListener('message', onMsg);
    window.parent.postMessage({ type: '__edit_mode_available' }, '*');
    return () => window.removeEventListener('message', onMsg);
  }, []);

  function persist(edits) {
    window.parent.postMessage({ type: '__edit_mode_set_keys', edits }, '*');
  }

  const currentTab = TABS.find(t => t.id === tab) || TABS[0];
  const Comp = window[currentTab.comp];

  return (
    <div>
      <div className="top-nav" data-screen-label={`00 ${currentTab.label}`}>
        <div className="nav-title">Paragraphos</div>
        {TABS.map(t => (
          <button key={t.id}
            className={`tab ${tab === t.id ? 'active' : ''}`}
            onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>

      {Comp ? <Comp showStatusbar={showStatusbar}/> : <div style={{padding:40}}>Loading…</div>}

      {editMode && (
        <div className="tweaks">
          <h4>Tweaks</h4>

          <label>
            <span>Sketchy</span>
            <div className="seg">
              <button className={sketchy ? 'on' : ''}
                onClick={() => { setSketchy(true); persist({ sketchy: true }); }}>sketch</button>
              <button className={!sketchy ? 'on' : ''}
                onClick={() => { setSketchy(false); persist({ sketchy: false }); }}>clean</button>
            </div>
          </label>

          <label>
            <span>Status bar</span>
            <div className="seg">
              <button className={showStatusbar ? 'on' : ''}
                onClick={() => { setShowStatusbar(true); persist({ showStatusbar: true }); }}>on</button>
              <button className={!showStatusbar ? 'on' : ''}
                onClick={() => { setShowStatusbar(false); persist({ showStatusbar: false }); }}>off</button>
            </div>
          </label>

          <label style={{alignItems:'flex-start', flexDirection:'column', gap:6}}>
            <span>Accent</span>
            <div className="seg" style={{width:'100%'}}>
              {Object.keys(ACCENTS).map(k => (
                <button key={k} className={accent === k ? 'on' : ''}
                  onClick={() => { setAccent(k); persist({ accent: k }); }}>{k}</button>
              ))}
            </div>
          </label>

          <div className="tiny muted" style={{marginTop:8, lineHeight:1.35}}>
            Use the top tabs to jump between screens. Press "clean" above to see the final-fidelity version of every layout.
          </div>
        </div>
      )}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
