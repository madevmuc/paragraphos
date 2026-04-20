// Shared components: MacWindow frame, ShellChrome (title/traffic/statusbar),
// tiny primitives like Pill, ProgressBar, TrafficLights.

const TRAFFIC = () => (
  <div className="mac-traffic">
    <span className="r"/><span className="y"/><span className="g"/>
  </div>
);

function MacWindow({ title = 'Paragraphos', children, height, caption, minWidth }) {
  return (
    <div className="variation" style={{ minWidth }}>
      <div className="mac-window" style={{ minHeight: height || 480 }}>
        <div className="mac-titlebar">
          <TRAFFIC />
          <div className="mac-title-text">{title}</div>
          <div style={{ width: 56 }} />
        </div>
        <div className="mac-body">{children}</div>
      </div>
      {caption && <div className="wf-caption">{caption}</div>}
    </div>
  );
}

function VariationLabel({ letter, name, note }) {
  return (
    <div className="variation-label">
      <span className="letter">{letter}</span>
      <span className="name">{name}</span>
      <span className="note">· {note}</span>
    </div>
  );
}

function Pill({ kind = 'idle', children }) {
  return (
    <span className={`pill ${kind}`}>
      <span className="dot"/> {children}
    </span>
  );
}

function Progress({ pct = 40 }) {
  return (
    <div className="progress">
      <div className="fill" style={{ width: pct + '%' }} />
    </div>
  );
}

function StatusBar({ variant = 'status', visible = true }) {
  if (!visible) return null;
  if (variant === 'status') {
    return (
      <div className="statusbar">
        <span className="dot run"/>
        <b>running</b>
        <span className="mono">3/12</span>
        <span className="sep">·</span>
        <span>started Mo, 20.04.2026 09:14</span>
        <span className="sep">·</span>
        <span>elapsed 18m</span>
        <span className="sep">·</span>
        <span>ETA 52m</span>
        <span className="sep">·</span>
        <span>finish ≈ 10:24</span>
      </div>
    );
  }
  return null;
}

function Toolbar({ children }) {
  return <div className="toolbar">{children}</div>;
}

// A rough "hand-drawn" separator for sketchy mode
function RoughLine({ y = 10, w = 200 }) {
  return (
    <svg width={w} height="4" style={{ display: 'block' }}>
      <path d={`M0,2 Q${w*0.25},${4} ${w*0.5},2 T${w},2`} stroke="#1a1a1a" strokeWidth="1" fill="none"/>
    </svg>
  );
}

// Annotation callout with a little arrow
function Callout({ children }) {
  return (
    <div className="callout">
      <svg width="18" height="22" viewBox="0 0 18 22" style={{ flexShrink: 0, marginTop: 2 }}>
        <path d="M2 20 Q 8 12 12 4 M12 4 L8 6 M12 4 L14 9" stroke="currentColor" strokeWidth="1.3" fill="none" strokeLinecap="round"/>
      </svg>
      <span>{children}</span>
    </div>
  );
}

Object.assign(window, {
  MacWindow, VariationLabel, Pill, Progress, StatusBar,
  Toolbar, TRAFFIC, RoughLine, Callout,
});
