import React, { useState, useEffect } from 'react';
import { 
  AreaChart, Area, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine 
} from 'recharts';
import { 
  TrendingUp, TrendingDown, DollarSign, Activity, Gauge, 
  ShieldAlert, Clock, RefreshCw, BarChart2, Zap, ArrowUpRight, ArrowDownRight, Layers, CheckCircle, AlertTriangle
} from 'lucide-react';

export default function TelemetryView() {
  const [health, setHealth] = useState(null);
  const [equityData, setEquityData] = useState([]);
  const [signals, setSignals] = useState([]);
  const [closedTrades, setClosedTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeChart, setActiveChart] = useState('equity'); // 'equity' | 'drawdown'
  const [actionFilter, setActionFilter] = useState('ALL');
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchTelemetryData = async () => {
    try {
      // 1. Fetch Health & Summary
      const healthRes = await fetch('http://localhost:8000/api/telemetry/health');
      if (healthRes.ok) {
        const hJson = await healthRes.json();
        setHealth(hJson);
      }

      // 2. Fetch Equity Curve
      const eqRes = await fetch('http://localhost:8000/api/telemetry/equity-curve?limit=300&format=json');
      if (eqRes.ok) {
        const eqJson = await eqRes.json();
        if (eqJson.data && Array.isArray(eqJson.data)) {
          const formatted = eqJson.data.map(item => ({
            time: new Date(item.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            total_equity: item.total_equity,
            drawdown: item.running_drawdown,
            realized_pnl: item.realized_pnl,
            unrealized_pnl: item.unrealized_pnl,
            hwm: item.high_water_mark,
          }));
          setEquityData(formatted);
        }
      }

      // 3. Fetch Signal History
      const sigRes = await fetch('http://localhost:8000/api/telemetry/signal-history?limit=100');
      if (sigRes.ok) {
        const sigJson = await sigRes.json();
        setSignals(sigJson.signals || []);
        setClosedTrades(sigJson.closed_trades || []);
      }
    } catch (e) {
      console.error('Failed to fetch telemetry data:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTelemetryData();
    let interval = null;
    if (autoRefresh) {
      interval = setInterval(fetchTelemetryData, 2000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [autoRefresh]);

  const portfolio = health?.portfolio || {};
  const position = health?.position || {};
  const initialBalance = 10000.0;
  const currentEquity = portfolio.total_equity || initialBalance;
  const totalReturnPct = ((currentEquity - initialBalance) / initialBalance) * 100.0;
  const realizedPnl = portfolio.realized_pnl || 0.0;
  const unrealizedPnl = position.unrealized_pnl || 0.0;
  const hwm = portfolio.high_water_mark || initialBalance;
  const drawdown = portfolio.running_drawdown_pct || 0.0;
  const maxDrawdown = portfolio.max_drawdown_pct || 0.0;

  // Filter signals
  const filteredSignals = signals.filter(sig => {
    if (actionFilter === 'ALL') return true;
    if (actionFilter === 'ENTRY') return sig.action.startsWith('ENTRY');
    if (actionFilter === 'EXIT') return sig.action.startsWith('EXIT');
    if (actionFilter === 'FLATTEN') return sig.action === 'FLATTEN';
    return sig.action === actionFilter;
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* ── TOP CONTROLS & HEADER ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: '18px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <BarChart2 size={20} color="#06b6d4" />
            Quant Telemetry & PnL Engine
          </h2>
          <p style={{ fontSize: '12px', color: 'var(--text-dim)', marginTop: '2px' }}>
            Real-time Non-blocking Mark-to-Market Portfolio Tracking & State of the World Decision Log
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button 
            className={`btn ${autoRefresh ? 'btn-bull' : 'btn-subtle'}`}
            style={{ fontSize: '12px', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '6px' }}
            onClick={() => setAutoRefresh(!autoRefresh)}
          >
            <RefreshCw size={14} className={autoRefresh ? 'spin-icon' : ''} />
            {autoRefresh ? 'Live Auto-Sync (2s)' : 'Paused'}
          </button>
          <button 
            className="btn btn-subtle" 
            style={{ fontSize: '12px', padding: '6px 12px' }}
            onClick={fetchTelemetryData}
          >
            Refresh Now
          </button>
        </div>
      </div>

      {/* ── KPI METRICS CARDS ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
        {/* Card 1: Total Equity */}
        <div className="glass-panel" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', color: 'var(--text-dim)' }}>
            <span>Total Equity</span>
            <DollarSign size={16} color="#06b6d4" />
          </div>
          <div className="mono" style={{ fontSize: '24px', fontWeight: 800, color: totalReturnPct >= 0 ? 'var(--accent-bull)' : 'var(--accent-bear)' }}>
            ${currentEquity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
            {totalReturnPct >= 0 ? <ArrowUpRight size={14} color="#10b981" /> : <ArrowDownRight size={14} color="#f43f5e" />}
            <span className="mono" style={{ color: totalReturnPct >= 0 ? 'var(--accent-bull)' : 'var(--accent-bear)', fontWeight: 600 }}>
              {totalReturnPct >= 0 ? `+${totalReturnPct.toFixed(2)}%` : `${totalReturnPct.toFixed(2)}%`}
            </span>
            <span style={{ color: 'var(--text-dim)' }}>vs $10k init</span>
          </div>
        </div>

        {/* Card 2: Realized & MtM PnL */}
        <div className="glass-panel" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', color: 'var(--text-dim)' }}>
            <span>Realized / Unrealized MtM</span>
            <Activity size={16} color="#a855f7" />
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '12px' }}>
            <span className="mono" style={{ fontSize: '20px', fontWeight: 700, color: realizedPnl >= 0 ? 'var(--accent-bull)' : 'var(--accent-bear)' }}>
              {realizedPnl >= 0 ? `+$${realizedPnl.toFixed(2)}` : `-$${Math.abs(realizedPnl).toFixed(2)}`}
            </span>
            <span className="mono" style={{ fontSize: '13px', color: unrealizedPnl >= 0 ? 'var(--accent-bull)' : 'var(--accent-bear)' }}>
              (MtM: {unrealizedPnl >= 0 ? `+$${unrealizedPnl.toFixed(2)}` : `-$${Math.abs(unrealizedPnl).toFixed(2)}`})
            </span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
            Closed Trades: <span className="mono" style={{ color: 'var(--text-main)' }}>{closedTrades.length} recorded</span>
          </div>
        </div>

        {/* Card 3: Drawdown & High Water Mark */}
        <div className="glass-panel" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', color: 'var(--text-dim)' }}>
            <span>Drawdown from Peak (HWM)</span>
            <ShieldAlert size={16} color={drawdown > 2.0 ? 'var(--accent-bear)' : '#f59e0b'} />
          </div>
          <div className="mono" style={{ fontSize: '24px', fontWeight: 800, color: drawdown > 0 ? 'var(--accent-bear)' : 'var(--accent-bull)' }}>
            {drawdown.toFixed(2)}%
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-dim)', display: 'flex', justifyContent: 'space-between' }}>
            <span>Max DD: <strong className="mono" style={{ color: 'var(--accent-bear)' }}>{maxDrawdown.toFixed(2)}%</strong></span>
            <span>HWM: <strong className="mono" style={{ color: 'var(--text-main)' }}>${hwm.toFixed(1)}</strong></span>
          </div>
        </div>

        {/* Card 4: Inventory & Bot Status */}
        <div className="glass-panel" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', color: 'var(--text-dim)' }}>
            <span>Active Position & Bot State</span>
            <Zap size={16} color="#10b981" />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span 
              className="mono" 
              style={{ 
                fontSize: '18px', 
                fontWeight: 700, 
                color: (position.size || 0) > 0 ? 'var(--accent-bull)' : (position.size || 0) < 0 ? 'var(--accent-bear)' : 'var(--text-muted)' 
              }}
            >
              {(position.size || 0) > 0 ? `+${position.size} BTC` : (position.size || 0) < 0 ? `${position.size} BTC` : 'FLAT (0.00)'}
            </span>
            <span 
              style={{ 
                fontSize: '10px', 
                padding: '2px 6px', 
                borderRadius: '4px', 
                fontWeight: 700,
                background: health?.status === 'RUNNING' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(244, 63, 94, 0.2)',
                color: health?.status === 'RUNNING' ? 'var(--accent-bull)' : 'var(--accent-bear)',
              }}
            >
              {health?.status || 'UNKNOWN'}
            </span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
            Entry: <span className="mono" style={{ color: 'var(--text-main)' }}>${(position.entry_price || 0).toFixed(1)}</span> | Mark: <span className="mono" style={{ color: 'var(--text-main)' }}>${(position.mark_price || 0).toFixed(1)}</span>
          </div>
        </div>
      </div>

      {/* ── EQUITY CURVE & DRAWDOWN CHART ── */}
      <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <TrendingUp size={18} color="#06b6d4" />
            <span style={{ fontSize: '15px', fontWeight: 700 }}>Real-Time Portfolio Equity Curve (1-Second Resolution)</span>
          </div>

          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              className={`btn ${activeChart === 'equity' ? 'btn-bull' : 'btn-subtle'}`}
              style={{ fontSize: '11px', padding: '4px 10px' }}
              onClick={() => setActiveChart('equity')}
            >
              Total Equity ($)
            </button>
            <button
              className={`btn ${activeChart === 'drawdown' ? 'btn-bear' : 'btn-subtle'}`}
              style={{ fontSize: '11px', padding: '4px 10px' }}
              onClick={() => setActiveChart('drawdown')}
            >
              Underwater Drawdown (%)
            </button>
          </div>
        </div>

        <div style={{ height: '280px', width: '100%', minHeight: '280px' }}>
          <ResponsiveContainer width="100%" height="100%">
            {activeChart === 'equity' ? (
              <AreaChart data={equityData} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                <defs>
                  <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.35}/>
                    <stop offset="95%" stopColor="#06b6d4" stopOpacity={0.0}/>
                  </linearGradient>
                </defs>
                <XAxis dataKey="time" stroke="#64748b" fontSize={10} tickMargin={6} />
                <YAxis 
                  stroke="#64748b" 
                  fontSize={10} 
                  domain={['dataMin - 50', 'dataMax + 50']}
                  tickFormatter={val => `$${val.toLocaleString()}`}
                />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#0f1420', borderColor: '#334155', borderRadius: '8px', fontSize: '12px' }}
                  itemStyle={{ color: '#06b6d4' }}
                />
                <ReferenceLine y={10000} stroke="#64748b" strokeDasharray="3 3" label={{ value: 'Initial $10k', fill: '#64748b', fontSize: 10, position: 'insideTopLeft' }} />
                <Area 
                  type="monotone" 
                  dataKey="total_equity" 
                  name="Total Equity ($)"
                  stroke="#06b6d4" 
                  strokeWidth={2} 
                  fillOpacity={1} 
                  fill="url(#equityGrad)" 
                  isAnimationActive={false} 
                />
              </AreaChart>
            ) : (
              <AreaChart data={equityData} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                <defs>
                  <linearGradient id="drawdownGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.4}/>
                    <stop offset="95%" stopColor="#f43f5e" stopOpacity={0.0}/>
                  </linearGradient>
                </defs>
                <XAxis dataKey="time" stroke="#64748b" fontSize={10} tickMargin={6} />
                <YAxis 
                  stroke="#64748b" 
                  fontSize={10} 
                  domain={[0, 'auto']}
                  tickFormatter={val => `-${val.toFixed(1)}%`}
                />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#0f1420', borderColor: '#334155', borderRadius: '8px', fontSize: '12px' }}
                  itemStyle={{ color: '#f43f5e' }}
                />
                <Area 
                  type="monotone" 
                  dataKey="drawdown" 
                  name="Drawdown (%)"
                  stroke="#f43f5e" 
                  strokeWidth={2} 
                  fillOpacity={1} 
                  fill="url(#drawdownGrad)" 
                  isAnimationActive={false} 
                />
              </AreaChart>
            )}
          </ResponsiveContainer>
        </div>
      </div>

      {/* ── SIGNAL TELEMETRY & DECISION SNAPSHOT LOG ── */}
      <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
          <div>
            <h3 style={{ fontSize: '15px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Layers size={18} color="#a855f7" />
              State of the World Decision Log (Exact Millisecond Snapshots)
            </h3>
            <p style={{ fontSize: '12px', color: 'var(--text-dim)', marginTop: '2px' }}>
              Captures Aggregated Mid-Price, MLOFI Imbalance, Multi-Exchange Z-Scores, VPIN, Footprint & Slippage
            </p>
          </div>

          <div style={{ display: 'flex', gap: '6px' }}>
            {['ALL', 'ENTRY', 'EXIT', 'FLATTEN'].map(f => (
              <button
                key={f}
                className={`btn ${actionFilter === f ? 'btn-bull' : 'btn-subtle'}`}
                style={{ fontSize: '11px', padding: '4px 10px' }}
                onClick={() => setActionFilter(f)}
              >
                {f}
              </button>
            ))}
          </div>
        </div>

        {/* Signals Table */}
        <div style={{ overflowX: 'auto', maxHeight: '420px', overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-dim)', position: 'sticky', top: 0, background: '#0a0d14' }}>
                <th style={{ padding: '8px 10px' }}>Time (Local)</th>
                <th style={{ padding: '8px 10px' }}>Action</th>
                <th style={{ padding: '8px 10px' }}>Mid Price / Spread</th>
                <th style={{ padding: '8px 10px' }}>MLOFI Imbalance</th>
                <th style={{ padding: '8px 10px' }}>Venue Z-Scores</th>
                <th style={{ padding: '8px 10px' }}>VPIN / Bucket</th>
                <th style={{ padding: '8px 10px' }}>Footprint / Absorbed</th>
                <th style={{ padding: '8px 10px' }}>Execution (Fill / Slippage)</th>
                <th style={{ padding: '8px 10px' }}>PnL Outcome</th>
              </tr>
            </thead>
            <tbody>
              {filteredSignals.length === 0 ? (
                <tr>
                  <td colSpan={9} style={{ textAlign: 'center', padding: '36px', color: 'var(--text-dim)' }}>
                    No strategy decision signals recorded yet in this session.
                    <div style={{ fontSize: '11px', marginTop: '6px', color: 'var(--accent-cyan)' }}>
                      Signals will automatically appear here when MLOFI/VPIN triggers an ENTRY, EXIT, or FLATTEN.
                    </div>
                  </td>
                </tr>
              ) : (
                filteredSignals.map((sig, idx) => {
                  const isLong = sig.action.includes('LONG') || sig.action === 'BUY';
                  const isShort = sig.action.includes('SHORT') || sig.action === 'SELL';
                  const isFlatten = sig.action === 'FLATTEN';
                  const isExit = sig.action.startsWith('EXIT');
                  
                  const exec = sig.execution_details || {};
                  const zScores = sig.z_scores || {};

                  return (
                    <tr key={idx} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)' }}>
                      {/* 1. Time */}
                      <td className="mono" style={{ padding: '10px', color: 'var(--text-muted)' }}>
                        {sig.iso_time ? sig.iso_time.split('T')[1].slice(0, 8) : new Date(sig.timestamp * 1000).toLocaleTimeString()}
                      </td>

                      {/* 2. Action Badge */}
                      <td style={{ padding: '10px' }}>
                        <span 
                          className="mono" 
                          style={{ 
                            padding: '3px 8px', 
                            borderRadius: '4px', 
                            fontSize: '11px', 
                            fontWeight: 700,
                            background: isLong 
                              ? 'rgba(16, 185, 129, 0.15)' 
                              : isShort 
                              ? 'rgba(244, 63, 94, 0.15)' 
                              : isFlatten
                              ? 'rgba(245, 158, 11, 0.15)'
                              : 'rgba(168, 85, 247, 0.15)',
                            color: isLong 
                              ? 'var(--accent-bull)' 
                              : isShort 
                              ? 'var(--accent-bear)' 
                              : isFlatten
                              ? 'var(--accent-warning)'
                              : 'var(--accent-purple)',
                            border: `1px solid ${
                              isLong ? 'rgba(16, 185, 129, 0.3)' : isShort ? 'rgba(244, 63, 94, 0.3)' : 'rgba(255, 255, 255, 0.1)'
                            }`
                          }}
                        >
                          {sig.action}
                        </span>
                      </td>

                      {/* 3. Mid Price / Spread */}
                      <td className="mono" style={{ padding: '10px' }}>
                        <div>${sig.mid_price.toLocaleString()}</div>
                        <div style={{ fontSize: '10px', color: 'var(--text-dim)' }}>Spread: ${sig.spread}</div>
                      </td>

                      {/* 4. MLOFI */}
                      <td className="mono" style={{ padding: '10px' }}>
                        <span style={{ color: sig.mlofi_score > 0 ? 'var(--accent-bull)' : sig.mlofi_score < 0 ? 'var(--accent-bear)' : 'var(--text-main)', fontWeight: 600 }}>
                          {sig.mlofi_score > 0 ? `+${sig.mlofi_score.toFixed(3)}` : sig.mlofi_score.toFixed(3)}
                        </span>
                      </td>

                      {/* 5. Venue Z-Scores */}
                      <td className="mono" style={{ padding: '10px', fontSize: '11px' }}>
                        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                          {Object.entries(zScores).slice(0, 3).map(([ex, z]) => (
                            <span key={ex} style={{ color: z > 1.0 ? 'var(--accent-bull)' : z < -1.0 ? 'var(--accent-bear)' : 'var(--text-dim)' }}>
                              {ex.slice(0, 3)}: {z.toFixed(1)}
                            </span>
                          ))}
                        </div>
                      </td>

                      {/* 6. VPIN & Bucket */}
                      <td className="mono" style={{ padding: '10px' }}>
                        <div>{(sig.vpin_value * 100).toFixed(1)}%</div>
                        <div style={{ fontSize: '10px', color: 'var(--text-dim)' }}>Bucket: {sig.bucket_size} BTC</div>
                      </td>

                      {/* 7. Footprint Delta & Absorption */}
                      <td className="mono" style={{ padding: '10px' }}>
                        <div style={{ color: sig.footprint_delta >= 0 ? 'var(--accent-bull)' : 'var(--accent-bear)' }}>
                          Δ {sig.footprint_delta > 0 ? `+${sig.footprint_delta.toFixed(2)}` : sig.footprint_delta.toFixed(2)}
                        </div>
                        {sig.is_absorption && (
                          <span style={{ fontSize: '10px', padding: '1px 4px', borderRadius: '3px', background: 'rgba(245, 158, 11, 0.2)', color: 'var(--accent-warning)' }}>
                            ABSORPTION
                          </span>
                        )}
                      </td>

                      {/* 8. Execution Details */}
                      <td className="mono" style={{ padding: '10px', fontSize: '11px' }}>
                        {exec.fill_price ? (
                          <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <span>${exec.fill_price.toLocaleString()} ({exec.fill_amount} BTC)</span>
                              {exec.status && (
                                <span style={{
                                  fontSize: '9px',
                                  padding: '1px 5px',
                                  borderRadius: '3px',
                                  fontWeight: 700,
                                  background: exec.status === 'FILLED' ? 'rgba(16, 185, 129, 0.2)' : exec.status === 'OPEN' ? 'rgba(59, 130, 246, 0.2)' : 'rgba(244, 63, 94, 0.2)',
                                  color: exec.status === 'FILLED' ? 'var(--accent-bull)' : exec.status === 'OPEN' ? '#3b82f6' : 'var(--accent-bear)'
                                }}>
                                  {exec.status}
                                </span>
                              )}
                            </div>
                            <div style={{ fontSize: '10px', color: 'var(--text-dim)' }}>
                              Slip: {exec.slippage_bps || 0} bps | RTT: {exec.rtt_ms || 0}ms
                              {exec.exchange_order_id && ` | tx: ${exec.exchange_order_id.slice(0, 8)}...`}
                            </div>
                          </div>
                        ) : (
                          <span style={{ color: 'var(--text-dim)' }}>Pending / None</span>
                        )}
                      </td>

                      {/* 9. Outcome / PnL */}
                      <td className="mono" style={{ padding: '10px', fontWeight: 700 }}>
                        {sig.pnl_usd !== null && sig.pnl_usd !== undefined ? (
                          <span style={{ color: sig.pnl_usd >= 0 ? 'var(--accent-bull)' : 'var(--accent-bear)' }}>
                            {sig.pnl_usd >= 0 ? `+$${sig.pnl_usd.toFixed(2)}` : `-$${Math.abs(sig.pnl_usd).toFixed(2)}`}
                          </span>
                        ) : (
                          <span style={{ color: 'var(--text-dim)' }}>—</span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
