import React from 'react';
import { Crosshair, ShieldAlert, Clock, ArrowUpRight, ArrowDownRight, XCircle, CheckCircle2, History } from 'lucide-react';

export default function ActivePositionTradesPanel({
  activePosition = {},
  activeOrder = {},
  recentTrades = [],
  onCancelOrder,
  onToggleKillSwitch,
  killSwitchActive = false,
}) {
  const hasPosition = activePosition?.side && activePosition?.size > 0;
  const posSide = activePosition?.side || 'FLAT';
  const posSize = activePosition?.size || 0.0;
  const entryPx = activePosition?.entry_price || 0.0;
  const slPx = activePosition?.sl || 0.0;
  const tpPx = activePosition?.tp || 0.0;
  const holdTime = activePosition?.hold_time_sec || 0.0;
  const minHoldRemaining = activePosition?.min_hold_remaining || 0.0;
  const unrealizedPnL = activePosition?.unrealized_pnl || 0.0;

  const hasActiveOrder = activeOrder?.id !== null && activeOrder?.id !== undefined;

  return (
    <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Panel Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Crosshair size={20} color="var(--accent-cyan)" />
          <h2 style={{ fontSize: '15px', fontWeight: 700, margin: 0, letterSpacing: '0.2px' }}>
            ACTIVE POSITION & EXECUTIONS
          </h2>
        </div>

        {/* Manual Kill Switch Button */}
        <button
          onClick={() => onToggleKillSwitch(!killSwitchActive)}
          className={`btn ${killSwitchActive ? 'btn-bull' : 'btn-danger'}`}
          style={{ padding: '6px 14px', fontSize: '12px', fontWeight: 700, letterSpacing: '0.5px' }}
        >
          <ShieldAlert size={14} />
          {killSwitchActive ? 'RESET KILL SWITCH' : 'EMERGENCY KILL SWITCH'}
        </button>
      </div>

      {/* Grid: Position Status + Active Order Status */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: '14px' }}>
        {/* Active Position Card */}
        <div
          style={{
            background: hasPosition
              ? posSide === 'BUY'
                ? 'rgba(16, 185, 129, 0.08)'
                : 'rgba(244, 63, 94, 0.08)'
              : 'rgba(10, 13, 20, 0.7)',
            border: `1px solid ${hasPosition ? (posSide === 'BUY' ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)') : 'var(--border-subtle)'}`,
            borderRadius: '8px',
            padding: '14px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
            <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              Current Position Inventory
            </span>
            <span
              className="mono"
              style={{
                fontSize: '11px',
                fontWeight: 700,
                padding: '2px 8px',
                borderRadius: '4px',
                background: hasPosition ? (posSide === 'BUY' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(244, 63, 94, 0.2)') : 'rgba(255, 255, 255, 0.08)',
                color: hasPosition ? (posSide === 'BUY' ? 'var(--accent-bull)' : 'var(--accent-bear)') : 'var(--text-dim)',
              }}
            >
              {hasPosition ? `${posSide === 'BUY' ? 'LONG' : 'SHORT'} (${posSize} BTC)` : 'FLAT / NO POSITION'}
            </span>
          </div>

          {hasPosition ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '8px' }}>
              <div>
                <div style={{ fontSize: '10px', color: 'var(--text-dim)' }}>Entry Price</div>
                <div className="mono" style={{ fontSize: '13px', fontWeight: 700 }}>${entryPx.toLocaleString()}</div>
              </div>
              <div>
                <div style={{ fontSize: '10px', color: 'var(--text-dim)' }}>Dynamic TP</div>
                <div className="mono" style={{ fontSize: '13px', fontWeight: 700, color: 'var(--accent-bull)' }}>${tpPx.toLocaleString()}</div>
              </div>
              <div>
                <div style={{ fontSize: '10px', color: 'var(--text-dim)' }}>Dynamic SL</div>
                <div className="mono" style={{ fontSize: '13px', fontWeight: 700, color: 'var(--accent-bear)' }}>${slPx.toLocaleString()}</div>
              </div>
              <div>
                <div style={{ fontSize: '10px', color: 'var(--text-dim)' }}>Hold Time</div>
                <div className="mono" style={{ fontSize: '13px', fontWeight: 700, color: holdTime >= 5.0 ? 'var(--accent-bull)' : 'var(--accent-warning)' }}>
                  {holdTime.toFixed(1)}s {minHoldRemaining > 0 ? `(Lock: ${minHoldRemaining.toFixed(1)}s)` : '✓'}
                </div>
              </div>
            </div>
          ) : (
            <div style={{ fontSize: '12px', color: 'var(--text-dim)', textAlign: 'center', padding: '10px 0' }}>
              Capital flat. RiskGuard ready for next institutional signal entry.
            </div>
          )}
        </div>

        {/* Active Resting Order Card (Cancel-Replace) */}
        <div style={{ background: 'rgba(10, 13, 20, 0.7)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '14px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              Resting Order (Cancel-Replace)
            </span>
            {hasActiveOrder && (
              <button
                onClick={() => onCancelOrder(activeOrder.id)}
                className="btn btn-subtle"
                style={{ padding: '2px 8px', fontSize: '10px', color: 'var(--accent-bear)' }}
              >
                Cancel #{activeOrder.id}
              </button>
            )}
          </div>

          {hasActiveOrder ? (
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0' }}>
              <div>
                <span className="mono" style={{ fontSize: '13px', fontWeight: 700, color: activeOrder.side === 'BUY' ? 'var(--accent-bull)' : 'var(--accent-bear)' }}>
                  {activeOrder.side}
                </span>{' '}
                <span className="mono" style={{ fontSize: '13px' }}>
                  @ ${activeOrder.price ? activeOrder.price.toLocaleString() : '-'}
                </span>
                <div style={{ fontSize: '10px', color: 'var(--text-dim)' }}>Order Index #{activeOrder.id}</div>
              </div>
              <span className="badge" style={{ background: 'rgba(6, 182, 212, 0.15)', color: 'var(--accent-cyan)', fontSize: '10px', padding: '2px 6px', borderRadius: '4px' }}>
                DRIFT PROTECTED (≤2 TICKS)
              </span>
            </div>
          ) : (
            <div style={{ fontSize: '12px', color: 'var(--text-dim)', textAlign: 'center', padding: '10px 0' }}>
              No resting order on Lighter book
            </div>
          )}
        </div>
      </div>

      {/* Last 10 Closed Trades Table */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px', fontSize: '12px', fontWeight: 700, color: 'var(--text-muted)' }}>
          <History size={14} />
          <span>LAST 10 CLOSED TRADES HISTORY</span>
        </div>

        <div style={{ overflowX: 'auto', border: '1px solid var(--border-subtle)', borderRadius: '8px', background: 'rgba(10, 13, 20, 0.6)' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '11px' }}>
            <thead>
              <tr style={{ background: 'rgba(15, 20, 32, 0.8)', borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}>
                <th style={{ padding: '8px 12px' }}>Timestamp</th>
                <th style={{ padding: '8px 12px' }}>Side</th>
                <th style={{ padding: '8px 12px' }}>Entry</th>
                <th style={{ padding: '8px 12px' }}>Exit</th>
                <th style={{ padding: '8px 12px' }}>Size</th>
                <th style={{ padding: '8px 12px' }}>Hold Time</th>
                <th style={{ padding: '8px 12px' }}>Signal / Action</th>
                <th style={{ padding: '8px 12px', textAlign: 'right' }}>Realized PnL</th>
              </tr>
            </thead>
            <tbody>
              {recentTrades && recentTrades.length > 0 ? (
                recentTrades.map((t, idx) => {
                  const pnl = t.realized_pnl || 0.0;
                  const isWin = pnl >= 0;
                  const timeStr = t.timestamp ? new Date(t.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '-';

                  return (
                    <tr key={idx} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)' }}>
                      <td style={{ padding: '8px 12px', color: 'var(--text-dim)' }} className="mono">{timeStr}</td>
                      <td style={{ padding: '8px 12px' }}>
                        <span style={{ color: t.side === 'BUY' ? 'var(--accent-bull)' : 'var(--accent-bear)', fontWeight: 700 }}>
                          {t.side}
                        </span>
                      </td>
                      <td style={{ padding: '8px 12px' }} className="mono">${t.entry_price?.toLocaleString() || '-'}</td>
                      <td style={{ padding: '8px 12px' }} className="mono">${t.exit_price?.toLocaleString() || '-'}</td>
                      <td style={{ padding: '8px 12px' }} className="mono">{t.size || '-'}</td>
                      <td style={{ padding: '8px 12px' }} className="mono">{t.holding_time_sec || 0}s</td>
                      <td style={{ padding: '8px 12px', color: 'var(--text-muted)' }}>{t.action || 'NORMAL'}</td>
                      <td style={{ padding: '8px 12px', textAlign: 'right' }} className="mono">
                        <span style={{ color: isWin ? 'var(--accent-bull)' : 'var(--accent-bear)', fontWeight: 700 }}>
                          {isWin ? '+' : ''}${pnl.toFixed(2)}
                        </span>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={8} style={{ padding: '16px', textAlign: 'center', color: 'var(--text-dim)' }}>
                    No closed trades recorded in this session.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
