import React from 'react';
import { Wifi, Activity, Clock, Layers, Gauge } from 'lucide-react';

export default function ExchangeHealthPanel({ exchangeHealth = {} }) {
  const connections = exchangeHealth.connections || {};
  const stalenessMs = exchangeHealth.staleness_ms || {};
  const volumeZScores = exchangeHealth.volume_z_scores || {};
  const marketWeights = exchangeHealth.market_weights || {};
  const rvolMultiplier = exchangeHealth.rvol_multiplier || 1.0;

  const exchanges = ['binance', 'bybit', 'hyperliquid', 'bitget', 'lighter'];

  return (
    <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Panel Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Wifi size={20} color="var(--accent-cyan)" />
          <h2 style={{ fontSize: '15px', fontWeight: 700, margin: 0, letterSpacing: '0.2px' }}>
            MULTI-EXCHANGE HEALTH & TIME SYNCHRONIZATION
          </h2>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            Dynamic RVOL: <strong style={{ color: 'var(--accent-cyan)' }}>{rvolMultiplier.toFixed(2)}x</strong>
          </span>
          <span className="badge" style={{ background: 'rgba(168, 85, 247, 0.15)', color: 'var(--accent-purple)', border: '1px solid rgba(168, 85, 247, 0.3)', padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 600 }}>
            100ms Logical Buckets
          </span>
        </div>
      </div>

      {/* Exchange Health Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '10px' }}>
        {exchanges.map((ex) => {
          const conn = connections[ex] || {};
          const isConn = conn.connected || false;
          const rtt = conn.rtt_ms || 0.0;
          const msgCount = conn.message_count || 0;
          const ageSec = conn.last_msg_age_sec !== undefined ? conn.last_msg_age_sec : 0.0;
          const drift = stalenessMs[ex] !== undefined ? stalenessMs[ex] : 0.0;
          const z = volumeZScores[ex] !== undefined ? volumeZScores[ex] : 0.0;
          const weight = marketWeights[ex] !== undefined ? (marketWeights[ex] * 100).toFixed(1) : '-';

          return (
            <div
              key={ex}
              style={{
                background: 'rgba(10, 13, 20, 0.7)',
                border: `1px solid ${isConn ? 'var(--border-subtle)' : 'rgba(244, 63, 94, 0.4)'}`,
                borderRadius: '8px',
                padding: '12px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
              }}
            >
              {/* Top row: Name + dot */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '12px', fontWeight: 800, textTransform: 'capitalize', color: 'var(--text-main)' }}>
                  {ex}
                </span>
                <span className={`status-dot ${isConn ? 'active' : 'inactive'}`} />
              </div>

              {/* RTT + Age */}
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-dim)' }}>
                <span>RTT:</span>
                <span className="mono" style={{ color: rtt < 150 ? 'var(--accent-bull)' : 'var(--accent-warning)', fontWeight: 600 }}>
                  {rtt}ms
                </span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-dim)' }}>
                <span>Last Msg:</span>
                <span className="mono" style={{ color: ageSec < 2.0 ? 'var(--text-main)' : 'var(--accent-bear)' }}>
                  {ageSec.toFixed(1)}s ago
                </span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-dim)' }}>
                <span>Sync Drift:</span>
                <span className="mono" style={{ color: drift < 200 ? 'var(--accent-bull)' : 'var(--accent-warning)' }}>
                  {drift.toFixed(0)}ms
                </span>
              </div>

              <div style={{ borderTop: '1px solid rgba(255, 255, 255, 0.05)', paddingTop: '6px', display: 'flex', justifyContent: 'space-between', fontSize: '10px' }}>
                <span style={{ color: 'var(--text-dim)' }}>Mkt Share:</span>
                <span className="mono" style={{ color: 'var(--accent-cyan)', fontWeight: 700 }}>{weight}%</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Volume Z-Score Heatmap Strip */}
      <div style={{ background: 'rgba(15, 20, 32, 0.6)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '12px 14px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
          <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
            Dynamic Normalization & Logical Clock Grid
          </span>
          <span style={{ fontSize: '10px', color: 'var(--text-dim)' }}>
            Authority: Local Receive Time (time.time_ns)
          </span>
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {exchanges.map((ex) => {
            const z = volumeZScores[ex] || 0.0;
            // Map z-score (-3 to +3) to color
            const intensity = Math.min(1.0, Math.abs(z) / 2.5);
            const color = z >= 0 ? `rgba(16, 185, 129, ${0.2 + intensity * 0.7})` : `rgba(244, 63, 94, ${0.2 + intensity * 0.7})`;

            return (
              <div
                key={ex}
                style={{
                  flex: 1,
                  background: color,
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  borderRadius: '4px',
                  padding: '6px 8px',
                  textAlign: 'center',
                }}
              >
                <div style={{ fontSize: '10px', textTransform: 'capitalize', color: '#fff', fontWeight: 600 }}>{ex}</div>
                <div className="mono" style={{ fontSize: '11px', fontWeight: 800, color: '#fff' }}>
                  {z > 0 ? '+' : ''}{z.toFixed(2)}σ
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
