import React from 'react';
import { Activity, ShieldAlert, Wifi, Zap, Lock } from 'lucide-react';

export default function Header({ connections = {}, risk = {}, onToggleKillSwitch }) {
  const isKillSwitchActive = risk?.kill_switch_active;
  const isToxic = risk?.passive_quoting_paused;

  return (
    <header className="app-header">
      <div className="brand-wrapper">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Zap size={22} color="#06b6d4" />
          <h1 style={{ fontSize: '18px', fontWeight: 800, letterSpacing: '-0.3px', margin: 0 }}>
            ORDERFLOW <span style={{ color: '#06b6d4' }}>HFT</span>
          </h1>
        </div>
        <span className="brand-badge">Lighter L2 ZK-Rollup</span>
        <div style={{ display: 'flex', alignItems: 'center', fontSize: '12px', color: 'var(--text-muted)' }}>
          <span className={`status-dot ${isKillSwitchActive ? 'danger' : 'active'}`}></span>
          {isKillSwitchActive ? 'HALTED (KILL-SWITCH)' : isToxic ? 'TOXIC VPIN (DEFENSIVE)' : 'LIVE EXECUTION'}
        </div>
      </div>

      {/* Venues telemetry */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        {['binance', 'hyperliquid', 'bitget', 'bybit', 'lighter'].map((venue) => {
          const conn = connections[venue] || {};
          const isConn = conn.connected;
          const rtt = conn.rtt_ms || 0;
          let rttColor = 'var(--accent-bull)';
          if (rtt > 150) rttColor = 'var(--accent-warning)';
          if (rtt > 300) rttColor = 'var(--accent-bear)';

          return (
            <div key={venue} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
              <span className={`status-dot ${isConn ? 'active' : 'inactive'}`}></span>
              <span style={{ textTransform: 'capitalize', color: 'var(--text-muted)' }}>{venue}</span>
              {isConn && (
                <span className="mono" style={{ color: rttColor, fontSize: '11px' }}>
                  {rtt}ms
                </span>
              )}
            </div>
          );
        })}

        {/* Desert Mode / L1 Indicator */}
        <div 
          title="Ethereum Layer 1 Rollup Desert Mode Escape Hatch Guard"
          style={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: '4px', 
            fontSize: '11px', 
            padding: '4px 8px', 
            borderRadius: '6px',
            background: risk?.desert_mode_active ? 'rgba(244,63,94,0.2)' : 'rgba(168,85,247,0.15)',
            border: `1px solid ${risk?.desert_mode_active ? 'var(--accent-bear)' : 'rgba(168,85,247,0.3)'}`,
            color: risk?.desert_mode_active ? 'var(--accent-bear)' : 'var(--accent-purple)'
          }}
        >
          <Lock size={12} />
          <span>Desert Mode: {risk?.desert_mode_active ? 'ACTIVE' : 'SAFE'}</span>
        </div>

        {/* Emergency Kill Switch Button */}
        <button
          onClick={() => onToggleKillSwitch(!isKillSwitchActive)}
          className={`btn ${isKillSwitchActive ? 'btn-bull' : 'btn-danger'}`}
          style={{ padding: '6px 14px', fontSize: '12px', letterSpacing: '0.3px' }}
        >
          <ShieldAlert size={14} />
          {isKillSwitchActive ? 'RE-ENABLE BOT' : 'KILL SWITCH'}
        </button>
      </div>
    </header>
  );
}
