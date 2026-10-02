import React, { useState, useEffect } from 'react';
import { Settings, Save, Play, Square, Activity, Zap } from 'lucide-react';

export default function BotConfigPanel({ botActive, onToggleBot }) {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchConfig();
  }, []);

  const fetchConfig = async () => {
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/api/bot/config');
      const data = await res.json();
      setConfig(data);
    } catch (err) {
      console.error("Failed to load config", err);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await fetch('http://localhost:8000/api/bot/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
    } catch (err) {
      console.error("Failed to save config", err);
    } finally {
      setSaving(false);
    }
  };

  const handleChange = (key, value) => {
    setConfig(prev => ({ ...prev, [key]: parseFloat(value) || value }));
  };

  if (!config) return <div className="glass-panel" style={{ padding: '20px' }}>Loading config...</div>;

  const currentLeverage = Number(config.leverage || 1.0);
  
  // FINAL_FIX #1C: Color-coded badge for current leverage (1x green, 2-5x yellow, >5x red)
  const getLeverageBadge = (lev) => {
    if (lev <= 1.0) {
      return { bg: 'rgba(16, 185, 129, 0.2)', border: 'var(--accent-bull)', color: 'var(--accent-bull)', text: '1x (Safety First)' };
    } else if (lev <= 5.0) {
      return { bg: 'rgba(245, 158, 11, 0.2)', border: 'var(--accent-warning)', color: 'var(--accent-warning)', text: `${lev}x (Moderate)` };
    } else {
      return { bg: 'rgba(244, 63, 94, 0.2)', border: 'var(--accent-bear)', color: 'var(--accent-bear)', text: `${lev}x (High Risk)` };
    }
  };

  const levBadge = getLeverageBadge(currentLeverage);

  return (
    <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div className="chart-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Settings size={18} color="var(--accent-cyan)" />
          <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700 }}>Autonomous Bot Configuration</h3>
          {/* Current Leverage Badge */}
          <span
            className="mono"
            style={{
              padding: '2px 8px',
              borderRadius: '4px',
              fontSize: '11px',
              fontWeight: 700,
              background: levBadge.bg,
              border: `1px solid ${levBadge.border}`,
              color: levBadge.color,
            }}
          >
            Leverage: {levBadge.text}
          </span>
        </div>

        <div style={{ display: 'flex', gap: '10px' }}>
          <button 
            className={`btn ${botActive ? 'btn-danger' : 'btn-bull'}`}
            onClick={() => onToggleBot(!botActive)}
          >
            {botActive ? <><Square size={16}/> Stop Bot</> : <><Play size={16}/> Start Bot</>}
          </button>
          <button className="btn btn-subtle" onClick={handleSave} disabled={saving}>
            <Save size={16} /> {saving ? 'Saving...' : 'Save Config'}
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
        {/* FINAL_FIX #1C: Leverage Selector Dropdown */}
        <div>
          <label className="metric-label" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Zap size={12} color="var(--accent-cyan)" /> Account Leverage (Cross)
          </label>
          <select
            className="form-input"
            value={currentLeverage}
            onChange={(e) => handleChange('leverage', e.target.value)}
            style={{ background: 'var(--bg-secondary)', color: 'var(--text-main)', cursor: 'pointer' }}
          >
            <option value="1">1x (Spot Equivalent / Zero Liquidation)</option>
            <option value="2">2x (Conservative Growth)</option>
            <option value="3">3x (Balanced Margin)</option>
            <option value="5">5x (Aggressive Momentum)</option>
            <option value="10">10x (High Velocity Scalp)</option>
            <option value="20">20x (Extreme HFT)</option>
          </select>
        </div>

        <div>
          <label className="metric-label">Risk Per Trade (%)</label>
          <input 
            type="number" 
            step="0.01" 
            className="form-input" 
            value={config.risk_per_trade_pct} 
            onChange={(e) => handleChange('risk_per_trade_pct', e.target.value)}
          />
        </div>

        <div>
          <label className="metric-label">Take Profit (%)</label>
          <input 
            type="number" 
            step="0.01" 
            className="form-input" 
            value={config.tp_percentage} 
            onChange={(e) => handleChange('tp_percentage', e.target.value)}
          />
        </div>

        <div>
          <label className="metric-label">Stop Loss (%)</label>
          <input 
            type="number" 
            step="0.01" 
            className="form-input" 
            value={config.sl_percentage} 
            onChange={(e) => handleChange('sl_percentage', e.target.value)}
          />
        </div>

        <div>
          <label className="metric-label">Max Active Positions</label>
          <input 
            type="number" 
            step="1" 
            className="form-input" 
            value={config.max_active_positions} 
            onChange={(e) => handleChange('max_active_positions', e.target.value)}
          />
        </div>

        <div>
          <label className="metric-label">VPIN Toxicity Threshold</label>
          <input 
            type="number" 
            step="0.01" 
            className="form-input" 
            value={config.vpin_toxicity_threshold} 
            onChange={(e) => handleChange('vpin_toxicity_threshold', e.target.value)}
          />
        </div>

        <div>
          <label className="metric-label">MLOFI Imbalance Threshold</label>
          <input 
            type="number" 
            step="0.01" 
            className="form-input" 
            value={config.mlofi_imbalance_threshold} 
            onChange={(e) => handleChange('mlofi_imbalance_threshold', e.target.value)}
          />
        </div>
      </div>
    </div>
  );
}
