import React from 'react';
import { ShieldCheck, ShieldAlert, CheckCircle2, XCircle, Clock, Zap, AlertTriangle, Activity } from 'lucide-react';

export default function RiskGuardStatusPanel({ riskGuard = {} }) {
  const killSwitchActive = riskGuard.kill_switch_active || false;
  const canOpen = riskGuard.can_open_position !== undefined ? riskGuard.can_open_position : true;
  const currentPositions = riskGuard.current_positions || 0;
  const maxPositions = riskGuard.max_concurrent_positions || 1;
  const dailyPnL = riskGuard.daily_pnl_usd || 0.0;
  const maxDailyLoss = riskGuard.max_daily_loss_usd || 100.0;
  const isLossCooldown = riskGuard.post_loss_cooldown_active || false;
  const cooldownSec = riskGuard.post_loss_cooldown_sec || 0.0;
  const rttMs = riskGuard.rtt_ms || 0.0;
  const stpBlocked = riskGuard.stp_blocked_count || 0;
  const desertModeActive = riskGuard.desert_mode_active || false;
  const alerts = riskGuard.alerts || [];

  // Evaluation of guards
  const isExposureSafe = currentPositions < maxPositions;
  const isDailyLossSafe = dailyPnL > -maxDailyLoss;
  const isCooldownReady = !isLossCooldown && cooldownSec <= 0.0;
  const isKillSwitchSafe = !killSwitchActive;
  const isRttSafe = rttMs < 350.0;

  return (
    <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Panel Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <ShieldCheck size={20} color="var(--accent-cyan)" />
          <h2 style={{ fontSize: '15px', fontWeight: 700, margin: 0, letterSpacing: '0.2px' }}>
            RISK GUARD & SURVIVAL ENGINE
          </h2>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Entry Engine Gate:</span>
          <span
            className="badge"
            style={{
              background: canOpen ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
              color: canOpen ? 'var(--accent-bull)' : 'var(--accent-bear)',
              border: `1px solid ${canOpen ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)'}`,
              padding: '2px 8px',
              borderRadius: '4px',
              fontSize: '11px',
              fontWeight: 700,
            }}
          >
            {canOpen ? 'CAN_OPEN_POSITION: TRUE' : 'GATE HALTED: FALSE'}
          </span>
        </div>
      </div>

      {/* Alert Banner if Triggered */}
      {(killSwitchActive || !isDailyLossSafe || isLossCooldown || desertModeActive) && (
        <div
          style={{
            background: 'rgba(244, 63, 94, 0.12)',
            border: '1px solid var(--accent-bear)',
            borderRadius: '8px',
            padding: '12px 16px',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            color: '#fff',
          }}
        >
          <AlertTriangle size={20} color="var(--accent-bear)" />
          <div style={{ fontSize: '12px' }}>
            <strong style={{ color: 'var(--accent-bear)' }}>RISK CONTROLS ENGAGED: </strong>
            {killSwitchActive && 'Kill Switch is currently active. '}
            {!isDailyLossSafe && `Daily loss threshold ($${maxDailyLoss}) breached. `}
            {isLossCooldown && `Anti-revenge cooldown active (${cooldownSec.toFixed(1)}s remaining). `}
            {desertModeActive && 'L1 Rollup Desert Mode detected! '}
          </div>
        </div>
      )}

      {/* Visual Risk Cards Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '10px' }}>
        {/* Guard 1: Exposure */}
        <div style={{ background: 'rgba(10, 13, 20, 0.7)', border: `1px solid ${isExposureSafe ? 'var(--border-subtle)' : 'var(--accent-warning)'}`, borderRadius: '8px', padding: '12px', textAlign: 'center' }}>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '6px' }}>
            {isExposureSafe ? <CheckCircle2 size={18} color="var(--accent-bull)" /> : <XCircle size={18} color="var(--accent-warning)" />}
          </div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Max Exposure</div>
          <div className="mono" style={{ fontSize: '13px', fontWeight: 700, marginTop: '2px' }}>
            {currentPositions} / {maxPositions} Pos
          </div>
        </div>

        {/* Guard 2: Daily Loss */}
        <div style={{ background: 'rgba(10, 13, 20, 0.7)', border: `1px solid ${isDailyLossSafe ? 'var(--border-subtle)' : 'var(--accent-bear)'}`, borderRadius: '8px', padding: '12px', textAlign: 'center' }}>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '6px' }}>
            {isDailyLossSafe ? <CheckCircle2 size={18} color="var(--accent-bull)" /> : <XCircle size={18} color="var(--accent-bear)" />}
          </div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Daily Loss ($100)</div>
          <div className="mono" style={{ fontSize: '13px', fontWeight: 700, marginTop: '2px', color: isDailyLossSafe ? 'var(--text-main)' : 'var(--accent-bear)' }}>
            ${Math.abs(Math.min(0, dailyPnL)).toFixed(1)} / ${maxDailyLoss}
          </div>
        </div>

        {/* Guard 3: Post-Loss Cooldown */}
        <div style={{ background: 'rgba(10, 13, 20, 0.7)', border: `1px solid ${isCooldownReady ? 'var(--border-subtle)' : 'var(--accent-warning)'}`, borderRadius: '8px', padding: '12px', textAlign: 'center' }}>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '6px' }}>
            {isCooldownReady ? <CheckCircle2 size={18} color="var(--accent-bull)" /> : <Clock size={18} color="var(--accent-warning)" />}
          </div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Loss Cooldown</div>
          <div className="mono" style={{ fontSize: '13px', fontWeight: 700, marginTop: '2px', color: isCooldownReady ? 'var(--accent-bull)' : 'var(--accent-warning)' }}>
            {isCooldownReady ? 'READY' : `${cooldownSec.toFixed(0)}s`}
          </div>
        </div>

        {/* Guard 4: Kill Switch */}
        <div style={{ background: 'rgba(10, 13, 20, 0.7)', border: `1px solid ${isKillSwitchSafe ? 'var(--border-subtle)' : 'var(--accent-bear)'}`, borderRadius: '8px', padding: '12px', textAlign: 'center' }}>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '6px' }}>
            {isKillSwitchSafe ? <CheckCircle2 size={18} color="var(--accent-bull)" /> : <XCircle size={18} color="var(--accent-bear)" />}
          </div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Kill Switch</div>
          <div className="mono" style={{ fontSize: '13px', fontWeight: 700, marginTop: '2px', color: isKillSwitchSafe ? 'var(--accent-bull)' : 'var(--accent-bear)' }}>
            {isKillSwitchSafe ? 'DISENGAGED' : 'ENGAGED'}
          </div>
        </div>

        {/* Guard 5: Network RTT Latency */}
        <div style={{ background: 'rgba(10, 13, 20, 0.7)', border: `1px solid ${isRttSafe ? 'var(--border-subtle)' : 'var(--accent-bear)'}`, borderRadius: '8px', padding: '12px', textAlign: 'center' }}>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '6px' }}>
            {isRttSafe ? <Activity size={18} color="var(--accent-bull)" /> : <AlertTriangle size={18} color="var(--accent-bear)" />}
          </div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Network RTT</div>
          <div className="mono" style={{ fontSize: '13px', fontWeight: 700, marginTop: '2px', color: rttMs < 150 ? 'var(--accent-bull)' : rttMs < 350 ? 'var(--accent-warning)' : 'var(--accent-bear)' }}>
            {rttMs.toFixed(1)} ms
          </div>
        </div>
      </div>

      {/* STP Blocked Counter & Recent Alerts */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(15, 20, 32, 0.5)', padding: '10px 14px', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
          Self-Trade Prevention (STP) blocked: <strong style={{ color: 'var(--accent-cyan)' }}>{stpBlocked} crosses</strong>
        </div>
        <div style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
          {alerts && alerts.length > 0 ? `Latest: ${alerts[alerts.length - 1]}` : 'System status nominal. Zero anomalies detected.'}
        </div>
      </div>
    </div>
  );
}
