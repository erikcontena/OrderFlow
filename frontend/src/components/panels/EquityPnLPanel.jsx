import React from 'react';
import { TrendingUp, TrendingDown, DollarSign, BarChart2, ShieldCheck, AlertCircle } from 'lucide-react';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';

export default function EquityPnLPanel({ equityPnL = {} }) {
  const totalEquity = equityPnL.total_equity || 10000.0;
  const realizedPnL = equityPnL.realized_pnl || 0.0;
  const unrealizedPnL = equityPnL.unrealized_pnl || 0.0;
  const dailyPnL = equityPnL.daily_pnl_usd || 0.0;
  const runningDrawdown = equityPnL.running_drawdown_pct || 0.0;
  const highWaterMark = equityPnL.high_water_mark || 10000.0;
  const tradesToday = equityPnL.closed_trades_today || 0;
  const snapshots = equityPnL.snapshots || [];

  // Format data for Recharts
  const chartData = snapshots.map((s, idx) => ({
    time: s.timestamp ? new Date(s.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : `${idx}s`,
    equity: Number(s.total_equity.toFixed(2)),
    drawdown: Number(s.running_drawdown.toFixed(2)),
  }));

  const isDailyProfitable = dailyPnL >= 0;
  const dailyLossPct = Math.min(100, Math.max(0, (Math.abs(Math.min(0, dailyPnL)) / 100.0) * 100));

  return (
    <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Panel Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <TrendingUp size={20} color="var(--accent-cyan)" />
          <h2 style={{ fontSize: '15px', fontWeight: 700, margin: 0, letterSpacing: '0.2px' }}>
            EQUITY CURVE & REAL-TIME PNL
          </h2>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            High-Water Mark: <strong style={{ color: 'var(--text-main)' }}>${highWaterMark.toLocaleString(undefined, { minimumFractionDigits: 2 })}</strong>
          </span>
          <span className="badge" style={{ background: 'rgba(6, 182, 212, 0.15)', color: 'var(--accent-cyan)', border: '1px solid rgba(6, 182, 212, 0.3)', padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 600 }}>
            {tradesToday} Trades Today
          </span>
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
        {/* Total Equity */}
        <div style={{ background: 'rgba(15, 20, 32, 0.6)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '12px' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>Total Portfolio Equity</div>
          <div className="mono" style={{ fontSize: '20px', fontWeight: 800, color: '#fff' }}>
            ${totalEquity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div style={{ fontSize: '11px', color: unrealizedPnL >= 0 ? 'var(--accent-bull)' : 'var(--accent-bear)', marginTop: '2px' }}>
            MtM: {unrealizedPnL >= 0 ? '+' : ''}${unrealizedPnL.toFixed(2)}
          </div>
        </div>

        {/* Daily PnL */}
        <div style={{ background: 'rgba(15, 20, 32, 0.6)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '12px' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>Daily PnL (RiskGuard)</div>
          <div className="mono" style={{ fontSize: '20px', fontWeight: 800, color: isDailyProfitable ? 'var(--accent-bull)' : 'var(--accent-bear)' }}>
            {isDailyProfitable ? '+' : ''}${dailyPnL.toFixed(2)}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
            Limit: -$100.00 / day
          </div>
        </div>

        {/* Realized PnL */}
        <div style={{ background: 'rgba(15, 20, 32, 0.6)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '12px' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>Cumulative Realized</div>
          <div className="mono" style={{ fontSize: '20px', fontWeight: 800, color: realizedPnL >= 0 ? 'var(--accent-bull)' : 'var(--accent-bear)' }}>
            {realizedPnL >= 0 ? '+' : ''}${realizedPnL.toFixed(2)}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
            Zero Lighter DEX fees
          </div>
        </div>

        {/* Running Drawdown */}
        <div style={{ background: 'rgba(15, 20, 32, 0.6)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '12px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Running Drawdown</span>
            <span className="mono" style={{ fontSize: '12px', fontWeight: 700, color: runningDrawdown > 2.0 ? 'var(--accent-bear)' : 'var(--accent-warning)' }}>
              {runningDrawdown.toFixed(2)}%
            </span>
          </div>
          {/* Visual progress bar */}
          <div style={{ width: '100%', height: '8px', background: 'rgba(255, 255, 255, 0.08)', borderRadius: '4px', overflow: 'hidden', marginTop: '8px' }}>
            <div
              style={{
                width: `${Math.min(100, runningDrawdown * 10)}%`,
                height: '100%',
                background: runningDrawdown > 2.0 ? 'linear-gradient(90deg, #f59e0b, #f43f5e)' : 'linear-gradient(90deg, #06b6d4, #10b981)',
                borderRadius: '4px',
                transition: 'width 0.3s ease',
              }}
            />
          </div>
          <div style={{ fontSize: '10px', color: 'var(--text-dim)', marginTop: '4px' }}>
            Daily loss budget used: {dailyLossPct.toFixed(0)}%
          </div>
        </div>
      </div>

      {/* Real-time Equity Area Chart */}
      <div style={{ width: '100%', height: '220px', background: 'rgba(10, 13, 20, 0.7)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '12px 12px 6px 0' }}>
        {chartData.length > 1 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#06b6d4" stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
              <XAxis dataKey="time" stroke="var(--text-dim)" fontSize={10} tickLine={false} />
              <YAxis
                domain={['auto', 'auto']}
                stroke="var(--text-dim)"
                fontSize={10}
                tickLine={false}
                tickFormatter={(val) => `$${val.toLocaleString()}`}
                orientation="right"
              />
              <Tooltip
                contentStyle={{
                  background: 'rgba(15, 20, 32, 0.95)',
                  border: '1px solid var(--accent-cyan)',
                  borderRadius: '6px',
                  fontSize: '11px',
                  boxShadow: '0 0 16px rgba(6, 182, 212, 0.25)',
                }}
                formatter={(val) => [`$${Number(val).toFixed(2)}`, 'Equity']}
              />
              <Area
                type="monotone"
                dataKey="equity"
                stroke="#06b6d4"
                strokeWidth={2}
                fillOpacity={1}
                fill="url(#equityGrad)"
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-dim)', fontSize: '12px' }}>
            Collecting real-time equity snapshots...
          </div>
        )}
      </div>
    </div>
  );
}
