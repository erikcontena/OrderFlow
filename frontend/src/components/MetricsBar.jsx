import React from 'react';
import { TrendingUp, TrendingDown, AlertTriangle, Gauge, Layers, DollarSign } from 'lucide-react';

export default function MetricsBar({ orderbooks = {}, vpin = {}, mlofi = {}, cvd = {} }) {
  // Use Binance as benchmark venue
  const binanceBook = orderbooks.binance || {};
  const midPrice = binanceBook.mid_price || 0.0;
  const spreadBps = binanceBook.spread_bps || 0.0;
  const spread = binanceBook.spread || 0.0;

  const vpinVal = vpin.vpin || 0.0;
  const isToxic = vpin.is_toxic;
  const percentile = vpin.percentile || 50.0;
  
  const mlofiVal = mlofi.weighted_mlofi || 0.0;
  const mlofiSignal = mlofi.signal || 'NEUTRAL';
  const cvdVal = cvd.cvd || 0.0;

  return (
    <div className="metrics-strip">
      {/* 1. Benchmark Mid Price */}
      <div className="glass-panel metric-card">
        <div className="metric-label">
          <span>BTC/USDT Benchmark (Binance)</span>
          <DollarSign size={14} color="#06b6d4" />
        </div>
        <div className="metric-value mono" style={{ color: '#06b6d4' }}>
          ${midPrice.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
        </div>
        <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>
          Spread: <span className="mono" style={{ color: 'var(--text-main)' }}>${spread.toFixed(1)}</span> ({spreadBps.toFixed(2)} bps)
        </div>
      </div>

      {/* 2. VPIN Toxicity Metric */}
      <div className="glass-panel metric-card" style={{ borderColor: isToxic ? 'var(--accent-bear)' : 'var(--border-subtle)' }}>
        <div className="metric-label">
          <span>VPIN Toxicity (Informed Flow)</span>
          <Gauge size={14} color={isToxic ? 'var(--accent-bear)' : 'var(--accent-warning)'} />
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
          <div className="metric-value mono" style={{ color: isToxic ? 'var(--accent-bear)' : 'var(--text-main)' }}>
            {(vpinVal * 100).toFixed(1)}%
          </div>
          <span 
            className="mono" 
            style={{ 
              fontSize: '11px', 
              padding: '2px 6px', 
              borderRadius: '4px',
              background: isToxic ? 'rgba(244,63,94,0.2)' : 'rgba(255,255,255,0.05)',
              color: isToxic ? 'var(--accent-bear)' : 'var(--text-muted)'
            }}
          >
            {percentile}th %ile
          </span>
        </div>
        <div style={{ fontSize: '11px', color: isToxic ? 'var(--accent-bear)' : 'var(--text-dim)', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
          {isToxic && <AlertTriangle size={12} />}
          <span>{isToxic ? 'TOXIC SPIKE: Maker Quoting Paused' : 'Flow Regime: Symmetrical / Safe'}</span>
        </div>
      </div>

      {/* 3. MLOFI Directional Pressure */}
      <div className="glass-panel metric-card">
        <div className="metric-label">
          <span>Multi-Level OFI (MLOFI)</span>
          <Layers size={14} color="var(--accent-purple)" />
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
          <div 
            className="metric-value mono" 
            style={{ color: mlofiVal > 0 ? 'var(--accent-bull)' : (mlofiVal < 0 ? 'var(--accent-bear)' : 'var(--text-main)') }}
          >
            {mlofiVal > 0 ? `+${mlofiVal.toFixed(2)}` : mlofiVal.toFixed(2)}
          </div>
          <span 
            style={{ 
              fontSize: '11px', 
              fontWeight: 700,
              color: mlofiSignal === 'BULLISH' ? 'var(--accent-bull)' : (mlofiSignal === 'BEARISH' ? 'var(--accent-bear)' : 'var(--text-dim)')
            }}
          >
            {mlofiSignal}
          </span>
        </div>
        {/* Visual imbalance bar */}
        <div style={{ height: '4px', width: '100%', background: 'rgba(255,255,255,0.1)', borderRadius: '2px', marginTop: '8px', position: 'relative', overflow: 'hidden' }}>
          <div 
            style={{ 
              position: 'absolute', 
              top: 0, 
              bottom: 0, 
              left: '50%',
              width: `${Math.min(50, Math.abs(mlofiVal) * 15)}%`,
              transform: mlofiVal < 0 ? 'translateX(-100%)' : 'none',
              background: mlofiVal >= 0 ? 'var(--accent-bull)' : 'var(--accent-bear)',
              transition: 'all 0.2s ease'
            }}
          />
        </div>
      </div>

      {/* 4. Cumulative Volume Delta (CVD) */}
      <div className="glass-panel metric-card">
        <div className="metric-label">
          <span>Cumulative Delta (CVD)</span>
          {cvdVal >= 0 ? <TrendingUp size={14} color="var(--accent-bull)" /> : <TrendingDown size={14} color="var(--accent-bear)" />}
        </div>
        <div 
          className="metric-value mono" 
          style={{ color: cvdVal >= 0 ? 'var(--accent-bull)' : 'var(--accent-bear)' }}
        >
          {cvdVal > 0 ? `+${cvdVal.toFixed(2)}` : cvdVal.toFixed(2)} <span style={{ fontSize: '13px', color: 'var(--text-dim)' }}>BTC</span>
        </div>
        <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>
          Aggressor Net Pressure
        </div>
      </div>
    </div>
  );
}
