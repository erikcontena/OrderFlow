import React, { useState, useEffect } from 'react';
import { Settings, Save, Play, Square, Activity } from 'lucide-react';

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
      // Optionally show a success toast here
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

  return (
    <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div className="chart-header">
        <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Settings size={18} /> Autonomous Bot Configuration
        </h3>
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

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
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
