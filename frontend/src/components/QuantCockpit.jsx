import React from 'react';
import EquityPnLPanel from './panels/EquityPnLPanel';
import SignalMonitorPanel from './panels/SignalMonitorPanel';
import ActivePositionTradesPanel from './panels/ActivePositionTradesPanel';
import RiskGuardStatusPanel from './panels/RiskGuardStatusPanel';
import ExchangeHealthPanel from './panels/ExchangeHealthPanel';

export default function QuantCockpit({
  telemetry = {},
  onCancelOrder,
  onToggleKillSwitch,
}) {
  const equityPnL = telemetry.equity_pnl || {
    total_equity: telemetry.execution?.equity_usd || 10000.0,
    realized_pnl: 0.0,
    unrealized_pnl: 0.0,
    daily_pnl_usd: telemetry.risk?.daily_pnl_usd || 0.0,
    running_drawdown_pct: 0.0,
    high_water_mark: telemetry.execution?.equity_usd || 10000.0,
    closed_trades_today: 0,
    snapshots: [],
  };

  const signalMonitor = telemetry.signal_monitor || {
    status_badge: telemetry.risk?.kill_switch_active ? 'KILL_SWITCH' : 'HOLD',
    signal_action: 'HOLD',
    signal_reason: 'Radar active',
    mlofi_imbalance: telemetry.mlofi?.weighted_mlofi || 0.0,
    z_scores: {},
    vpin_value: telemetry.vpin?.vpin || 0.0,
    vpin_threshold: telemetry.vpin?.toxicity_threshold || 0.85,
    vpin_is_toxic: telemetry.vpin?.is_toxic || false,
    footprint_delta_recent: 0.0,
    cooldown_remaining_sec: 0.0,
    loss_cooldown_remaining_sec: 0.0,
  };

  const activePosition = telemetry.active_position || {
    side: null,
    entry_price: 0.0,
    size: 0.0,
    sl: 0.0,
    tp: 0.0,
    hold_time_sec: 0.0,
    min_hold_remaining: 0.0,
    unrealized_pnl: 0.0,
  };

  const activeOrder = telemetry.active_order || {
    id: null,
    price: null,
    side: null,
  };

  const recentTrades = telemetry.recent_trades || [];

  const riskGuard = telemetry.risk_guard || {
    kill_switch_active: telemetry.risk?.kill_switch_active || false,
    can_open_position: true,
    current_positions: telemetry.risk?.current_positions || 0,
    max_concurrent_positions: 1,
    daily_pnl_usd: telemetry.risk?.daily_pnl_usd || 0.0,
    max_daily_loss_usd: 100.0,
    post_loss_cooldown_active: false,
    post_loss_cooldown_sec: 0.0,
    stp_blocked_count: telemetry.risk?.stp_blocked_count || 0,
    desert_mode_active: telemetry.risk?.desert_mode_active || false,
    alerts: telemetry.risk?.recent_alerts || [],
    rtt_ms: telemetry.execution?.rtt_ms || 0.0,
  };

  const exchangeHealth = telemetry.exchange_health || {
    connections: telemetry.connections || {},
    staleness_ms: {},
    volume_z_scores: {},
    market_weights: {},
    rvol_multiplier: 1.0,
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', padding: '0 24px 24px' }}>
      {/* Top Row: Panel 1 (Equity Curve & PnL) + Panel 2 (Signal Monitor) */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '20px' }}>
        <EquityPnLPanel equityPnL={equityPnL} />
        <SignalMonitorPanel signalMonitor={signalMonitor} footprintBars={telemetry.footprint_bars} />
      </div>

      {/* Middle Row: Panel 3 (Active Position & Recent Trades) */}
      <ActivePositionTradesPanel
        activePosition={activePosition}
        activeOrder={activeOrder}
        recentTrades={recentTrades}
        onCancelOrder={onCancelOrder}
        onToggleKillSwitch={onToggleKillSwitch}
        killSwitchActive={riskGuard.kill_switch_active}
      />

      {/* Bottom Row: Panel 4 (Risk Guard Status) + Panel 5 (Exchange Health) */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
        <RiskGuardStatusPanel riskGuard={riskGuard} />
        <ExchangeHealthPanel exchangeHealth={exchangeHealth} />
      </div>
    </div>
  );
}
