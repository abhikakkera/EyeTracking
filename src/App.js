import React, { useEffect, useRef, useState } from 'react';

const MIN_CALIBRATION = 10;

function App() {
  const [gazeData, setGazeData] = useState(null);
  const [status, setStatus] = useState('loading');
  const [calPoints, setCalPoints] = useState(0);
  const [flash, setFlash] = useState(false);
  const mouseRef = useRef({ x: 0, y: 0 });
  const startedRef = useRef(false);
  const webgazerRef = useRef(null);

  useEffect(() => {
    let active = true;

    async function init() {
      const wg = window.webgazer;
      if (!wg) { setStatus('error'); return; }
      webgazerRef.current = wg;

      wg.clearData();
      wg.params.faceMeshSolutionPath = 'https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh@0.4.1633559619';

      wg.setGazeListener((data) => {
        if (!active || !data) return;
        setGazeData({ x: Math.round(data.x), y: Math.round(data.y) });
      })
        .setRegression('ridge')
        .applyKalmanFilter(true)
        .showPredictionPoints(true)
        .showVideo(true)
        .showFaceOverlay(true);

      try { await wg.begin(); } catch (e) { console.warn(e); }
      startedRef.current = true;
      if (active) setStatus('calibrating');
    }

    init();

    // Track mouse position at all times
    const onMouseMove = (e) => {
      mouseRef.current = { x: e.clientX, y: e.clientY };
    };

    // Cmd+Shift = record current mouse position as calibration point
    const onKeyDown = (e) => {
      if (e.metaKey && e.shiftKey && webgazerRef.current && startedRef.current) {
        const { x, y } = mouseRef.current;
        try {
          webgazerRef.current.recordScreenPosition(x, y, 'click');
        } catch (_) {}
        setCalPoints(c => {
          const next = c + 1;
          return next;
        });
        // Flash feedback
        setFlash(true);
        setTimeout(() => setFlash(false), 200);
      }
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('keydown', onKeyDown);

    return () => {
      active = false;
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('keydown', onKeyDown);
      if (startedRef.current && window.webgazer) {
        try { window.webgazer.end(); } catch (_) {}
      }
    };
  }, []);

  const calibrated = calPoints >= MIN_CALIBRATION;

  if (status === 'loading') {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', fontFamily: 'Arial', flexDirection: 'column', gap: 12 }}>
        <div style={{ fontSize: 22, fontWeight: 'bold' }}>Starting camera...</div>
        <div style={{ color: '#666' }}>Allow webcam access if prompted</div>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', fontFamily: 'Arial', color: '#c62828' }}>
        Camera error — allow webcam access and refresh
      </div>
    );
  }

  return (
    <>
      {/* Flash overlay on calibration point recorded */}
      {flash && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(255,255,255,0.3)', zIndex: 9999, pointerEvents: 'none' }} />
      )}

      <div style={{ padding: '20px', fontFamily: 'Arial, sans-serif', maxWidth: '900px', margin: '0 auto' }}>
        <h1 style={{ textAlign: 'center', marginBottom: '10px' }}>Eye Gaze Tracking</h1>

        {/* Status bar */}
        <div style={{
          padding: '14px',
          background: calibrated ? '#4ade80' : '#f97316',
          color: 'white',
          borderRadius: '8px',
          marginBottom: '20px',
          fontWeight: 'bold',
          fontSize: '16px',
          textAlign: 'center',
        }}>
          {calibrated ? 'Tracking active' : `Calibrating — ${calPoints}/${MIN_CALIBRATION} points recorded`}
        </div>

        {/* Calibration instructions */}
        <div style={{ padding: '16px', background: '#f0f0f0', borderRadius: '8px', marginBottom: '20px', border: '1px solid #ddd' }}>
          <p style={{ margin: '0 0 10px 0' }}><strong>How to calibrate:</strong></p>
          <ol style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8 }}>
            <li>Move your mouse to a spot on the screen</li>
            <li><strong>Look at where the cursor is</strong></li>
            <li>Press <kbd style={{ background: '#fff', border: '1px solid #ccc', borderRadius: '4px', padding: '2px 6px' }}>⌘ Cmd</kbd> + <kbd style={{ background: '#fff', border: '1px solid #ccc', borderRadius: '4px', padding: '2px 6px' }}>Shift</kbd> to record that point</li>
            <li>Repeat across different parts of the screen ({MIN_CALIBRATION} points minimum)</li>
          </ol>
          <p style={{ margin: '10px 0 0 0', color: '#555', fontSize: '14px' }}>
            Tip: cover all corners and the center for best accuracy. Press Cmd+Shift anytime to add more points.
          </p>
        </div>

        {/* Calibration progress */}
        <div style={{ marginBottom: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px', fontSize: '14px', color: '#555' }}>
            <span>Calibration points</span>
            <span>{calPoints} recorded</span>
          </div>
          <div style={{ height: '8px', background: '#e0e0e0', borderRadius: '4px' }}>
            <div style={{
              width: `${Math.min(calPoints / MIN_CALIBRATION * 100, 100)}%`,
              height: '100%',
              background: calibrated ? '#4ade80' : '#f97316',
              borderRadius: '4px',
              transition: 'width 0.2s ease',
            }} />
          </div>
        </div>

        {/* Gaze data */}
        {calibrated && gazeData && (
          <div style={{ padding: '20px', background: '#e8f5e9', borderRadius: '8px', border: '2px solid #4ade80' }}>
            <h2 style={{ marginTop: 0, color: '#2e7d32' }}>Gaze Position:</h2>
            <div style={{ fontSize: '18px', fontFamily: 'monospace', lineHeight: 2 }}>
              <p><strong>X:</strong> <span style={{ color: '#1976d2', fontSize: '28px', fontWeight: 'bold' }}>{gazeData.x}px</span> <span style={{ fontSize: '13px', color: '#888' }}>from left</span></p>
              <p><strong>Y:</strong> <span style={{ color: '#d32f2f', fontSize: '28px', fontWeight: 'bold' }}>{gazeData.y}px</span> <span style={{ fontSize: '13px', color: '#888' }}>from top</span></p>
            </div>
          </div>
        )}

        {calibrated && !gazeData && (
          <div style={{ padding: '20px', background: '#ffebee', borderRadius: '8px', textAlign: 'center', color: '#c62828' }}>
            Waiting for gaze prediction — make sure your face is in the webcam frame
          </div>
        )}

        {/* Recalibrate button */}
        {calibrated && (
          <div style={{ textAlign: 'center', marginTop: '16px' }}>
            <button
              onClick={() => { setCalPoints(0); setGazeData(null); webgazerRef.current?.clearData(); }}
              style={{ padding: '10px 24px', background: '#3b82f6', color: 'white', border: 'none', borderRadius: '6px', fontSize: '15px', cursor: 'pointer' }}
            >
              Reset & Recalibrate
            </button>
          </div>
        )}
      </div>
    </>
  );
}

export default App;
