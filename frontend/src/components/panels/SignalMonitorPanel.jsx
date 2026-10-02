import React from 'react';
import { Radio, AlertTriangle, ShieldCheck, Flame, PauseCircle, Clock, Zap } from 'lucide-react';

export default function SignalMonitorPanel({ signalMonitor = {}, footprintBars = [] }) {
  const statusBadge = signalMonitor.status_badge || 'HOLD';
  const signalAction = signalMonitor.signal_action || 'HOLD';
  const signalReason = signalMonitor.signal_reason || 'Scanning market microstructure';
  const mlofiImbalance = signalMonitor.mlofi_imbalance || 0.0;
  const zScores = signalMonitor.z_scores || {};
  const vpinVal = signalMonitor.vpin_value || 0.0;
  const vpinThreshold = signalMonitor.vpin_threshold || 0.85;
  const vpinIsToxic = signalMonitor.vpin_is_toxic || false;
  const cooldownRem = signalMonitor.cooldown_remaining_sec || 0.0;
  const lossCooldownRem = signalMonitor.loss_cooldown_remaining_sec || 0.0;

  // Determine badge color and glow
  const getBadgeStyle = () => {
    switch (statusBadge) {
      case 'BUY':
        return {
          bg: 'rgba(16, 185, 129, 0.2)',
          border: 'var(--accent-bull)',
          color: 'var(--accent-bull)',
          shadow: '0 0 16px rgba(16, 185, 129, 0.4)',
          text: 'BUY (LONG MOMENTUM)',
          icon: <Flame size={16} />
        };
      case 'SELL':
        return {
          bg: 'rgba(244, 63, 94, 0.2)',
          border: 'var(--accent-bear)',
          color: 'var(--accent-bear)',
          shadow: '0 0 16px rgba(244, 63, 94, 0.4)',
          text: 'SELL (SHORT ABSORPTION)',
          icon: <Zap size={16} />
        };
      case 'COOLDOWN':
        return {
          bg: 'rgba(245, 158, 11, 0.2)',
          border: 'var(--accent-warning)',
          color: 'var(--accent-warning)',
          shadow: '0 0 16px rgba(245, 158, 11, 0.4)',
          text: `COOLDOWN (${Math.max(cooldownRem, lossCooldownRem).toFixed(1)}s)`,
          icon: <Clock size={16} />
        };
      case 'KILL_SWITCH':
        return {
          bg: 'rgba(244, 63, 94, 0.3)',
          border: 'var(--accent-bear)',
          color: '#fff',
          shadow: '0 0 24px rgba(244, 63, 94, 0.6)',
          text: 'KILL SWITCH ENGAGED',
          icon: <AlertTriangle size={16} />
        };
      default:
        if (statusBadge.startsWith('POSITION_')) {
          const side = statusBadge.replace('POSITION_', '');
          return {
            bg: side === 'BUY' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
            border: side === 'BUY' ? 'var(--accent-bull)' : 'var(--accent-bear)',
            color: side === 'BUY' ? 'var(--accent-bull)' : 'var(--accent-bear)',
            shadow: '0 0 12px rgba(6, 182, 212, 0.3)',
            text: `IN POSITION (${side})`,
            icon: <ShieldCheck size={16} />
          };
        }
        return {
          bg: 'rgba(100, 116, 139, 0.2)',
          border: 'rgba(255, 255, 255, 0.15)',
          color: 'var(--text-muted)',
          shadow: 'none',
          text: 'RADAR ACTIVE: HOLD',
          icon: <Radio size={16} />
        };
    }
  };

  const badge = getBadgeStyle();
  const exchanges = ['binance', 'bybit', 'hyperliquid', 'bitget', 'lighter'];

  // VPIN percentage (capped 0-100)
  const vpinPct = Math.min(100, Math.max(0, vpinVal * 100));

  return (
    <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Panel Header & Badge */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Radio size={20} color="var(--accent-cyan)" />
          <h2 style={{ fontSize: '15px', fontWeight: 700, margin: 0, letterSpacing: '0.2px' }}>
            QUANT SIGNAL MONITOR & FLOW
          </h2>
        </div>

        {/* Dynamic Status Badge */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            background: badge.bg,
            border: `1px solid ${badge.border}`,
            color: badge.color,
            boxShadow: badge.shadow,
            padding: '6px 14px',
            borderRadius: '20px',
            fontSize: '12px',
            fontWeight: 800,
            letterSpacing: '0.5px',
            textTransform: 'uppercase',
          }}
        >
          {badge.icon}
          <span>{badge.text}</span>
        </div>
      </div>

      {/* Signal Reason Callout */}
      <div style={{ background: 'rgba(15, 20, 32, 0.7)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '10px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
          Strategy Engine: <span style={{ color: 'var(--text-main)', fontWeight: 600 }}>{signalReason}</span>
        </div>
        <div className="mono" style={{ fontSize: '11px', color: 'var(--accent-cyan)' }}>
          Action: {signalAction}
        </div>
      </div>

      {/* Grid: VPIN Gauge + MLOFI & Normalizer Z-Scores */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        {/* VPIN Gauge Box */}
        <div style={{ background: 'rgba(10, 13, 20, 0.7)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '14px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)' }}>VPIN Toxicity Flow</span>
            <span
              className="mono"
              style={{
                fontSize: '14px',
                fontWeight: 800,
                color: vpinIsToxic ? 'var(--accent-bear)' : vpinVal > 0.65 ? 'var(--accent-warning)' : 'var(--accent-bull)',
              }}
            >
              {vpinVal.toFixed(3)}
            </span>
          </div>

          {/* VPIN Progress Bar */}
          <div style={{ position: 'relative', width: '100%', height: '14px', background: 'rgba(255, 255, 255, 0.08)', borderRadius: '7px', overflow: 'hidden' }}>
            <div
              style={{
                width: `${vpinPct}%`,
                height: '100%',
                background: vpinVal > vpinThreshold
                  ? 'linear-gradient(90deg, #f59e0b, #f43f5e)'
                  : vpinVal > 0.65
                  ? 'linear-gradient(90deg, #10b981, #f59e0b)'
                  : 'linear-gradient(90deg, #06b6d4, #10b981)',
                borderRadius: '7px',
                transition: 'width 0.3s ease',
              }}
            />
            {/* Cutoff marker line at 0.85 */}
            <div
              style={{
                position: 'absolute',
                left: `${vpinThreshold * 100}%`,
                top: 0,
                bottom: 0,
                width: '2px',
                background: '#fff',
                boxShadow: '0 0 6px #f43f5e',
                zIndex: 2,
              }}
              title="Kill Switch Threshold (0.85)"
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--text-dim)', marginTop: '6px' }}>
            <span>0.00 (Pure Flow)</span>
            <span style={{ color: 'var(--accent-bear)', fontWeight: 600 }}>Toxicity Barrier: {vpinThreshold}</span>
            <span>1.00 (Adverse)</span>
          </div>
        </div>

        {/* MLOFI Aggregated Imbalance */}
        <div style={{ background: 'rgba(10, 13, 20, 0.7)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '14px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)' }}>MLOFI Multi-Level Imbalance</span>
            <span
              className="mono"
              style={{
                fontSize: '14px',
                fontWeight: 800,
                color: mlofiImbalance > 0 ? 'var(--accent-bull)' : mlofiImbalance < 0 ? 'var(--accent-bear)' : 'var(--text-muted)',
              }}
            >
              {mlofiImbalance > 0 ? '+' : ''}{mlofiImbalance.toFixed(4)}
            </span>
          </div>

          {/* Bi-directional Center Balance Bar */}
          <div style={{ position: 'relative', width: '100%', height: '14px', background: 'rgba(255, 255, 255, 0.08)', borderRadius: '7px' }}>
            {/* Midline at 50% */}
            <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: '2px', background: 'rgba(255, 255, 255, 0.3)', zIndex: 2 }} />

            {mlofiImbalance >= 0 ? (
              <div
                style={{
                  position: 'absolute',
                  left: '50%',
                  width: `${Math.min(50, mlofiImbalance * 50)}%`,
                  height: '100%',
                  background: 'linear-gradient(90deg, #06b6d4, #10b981)',
                  borderRadius: '0 7px 7px 0',
                  transition: 'width 0.2s ease',
                }}
              />
            ) : (
              <div
                style={{
                  position: 'absolute',
                  right: '50%',
                  width: `${Math.min(50, Math.abs(mlofiImbalance) * 50)}%`,
                  height: '100%',
                  background: 'linear-gradient(270deg, #a855f7, #f43f5e)',
                  borderRadius: '7px 0 0 7px',
                  transition: 'width 0.2s ease',
                }}
              />
            )}
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--text-dim)', marginTop: '6px' }}>
            <span>-1.0 (Ask Dominance)</span>
            <span>Balanced (0.0)</span>
            <span>+1.0 (Bid Dominance)</span>
          </div>
        </div>
      </div>

      {/* Z-Scores Per Exchange (Welford O(1)) */}
      <div style={{ background: 'rgba(10, 13, 20, 0.7)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '12px 14px' }}>
        <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '8px' }}>
          Normalized Volume Z-Scores (30m Welford Window)
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '10px' }}>
          {exchanges.map((ex) => {
            const z = zScores[ex] !== undefined ? zScores[ex] : 0.0;
            const isHigh = Math.abs(z) > 1.5;
            return (
              <div key={ex} style={{ background: 'rgba(15, 20, 32, 0.5)', padding: '8px', borderRadius: '6px', textAlign: 'center', border: `1px solid ${isHigh ? 'rgba(6,182,212,0.3)' : 'var(--border-subtle)'}` }}>
                <div style={{ fontSize: '10px', color: 'var(--text-dim)', textTransform: 'capitalize' }}>{ex}</div>
                <div className="mono" style={{ fontSize: '13px', fontWeight: 700, color: z > 0.5 ? 'var(--accent-bull)' : z < -0.5 ? 'var(--accent-bear)' : 'var(--text-muted)' }}>
                  {z > 0 ? '+' : ''}{z.toFixed(2)}σ
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Footprint Delta Mini-Bars */}
      {footprintBars && footprintBars.length > 0 && (
        <div style={{ background: 'rgba(10, 13, 20, 0.7)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '12px 14px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              Footprint CVD Delta Flow (Last {footprintBars.length} Bars)
            </span>
            <span className="mono" style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
              Latest: {footprintBars[footprintBars.length - 1]?.delta?.toFixed(2) || 0} BTC
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', height: '40px' }}>
            {footprintBars.map((bar, i) => {
              const d = bar.delta || 0;
              const isPos = d >= 0;
              const heightPct = Math.min(100, Math.max(15, Math.abs(d) * 20));
              return (
                <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
                  <div
                    title={`Bar ${i + 1}: ${d.toFixed(2)} BTC`}
                    style={{
                      width: '80%',
                      height: `${heightPct}%`,
                      background: isPos ? 'var(--accent-bull)' : 'var(--accent-bear)',
                      borderRadius: '2px',
                      transition: 'height 0.2s ease',
                    }}
                  />
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
