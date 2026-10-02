import React from 'react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { Activity } from 'lucide-react';

export default function CvdChart({ cvd = {} }) {
  const points = (cvd.points || []).map(p => ({
    time: new Date(p.timestamp * 1000).toLocaleTimeString(),
    cvd: p.cvd
  }));

  const minCvd = points.length ? Math.min(...points.map(p => p.cvd)) : 0;
  const maxCvd = points.length ? Math.max(...points.map(p => p.cvd)) : 100;

  return (
    <div className="glass-panel" style={{ padding: '16px', display: 'flex', flexDirection: 'column', minHeight: '220px', flex: 1 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Activity size={16} color="#06b6d4" />
          <span style={{ fontSize: '13px', fontWeight: 700 }}>Cumulative Volume Delta (CVD) Stream</span>
        </div>
        <span className="mono" style={{ fontSize: '12px', color: (cvd.cvd || 0) >= 0 ? 'var(--accent-bull)' : 'var(--accent-bear)', fontWeight: 700 }}>
          {(cvd.cvd || 0) > 0 ? `+${(cvd.cvd || 0).toFixed(2)}` : (cvd.cvd || 0).toFixed(2)} BTC
        </span>
      </div>

      <div style={{ flex: 1, minHeight: '140px', width: '100%', marginTop: '8px' }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={points} margin={{ top: 10, right: 0, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="colorCvd" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.4}/>
                <stop offset="95%" stopColor="#06b6d4" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <XAxis dataKey="time" hide={true} />
            <YAxis 
              stroke="#64748b" 
              fontSize={10} 
              domain={[minCvd - Math.abs(minCvd * 0.1), maxCvd + Math.abs(maxCvd * 0.1)]} 
              tickCount={5}
            />
            <Tooltip 
              contentStyle={{ backgroundColor: '#0f1420', borderColor: '#334155', borderRadius: '8px', fontSize: '12px' }}
              itemStyle={{ color: '#06b6d4' }}
              labelStyle={{ color: '#64748b' }}
            />
            <Area 
              type="monotone" 
              dataKey="cvd" 
              stroke="#06b6d4" 
              strokeWidth={2}
              fillOpacity={1} 
              fill="url(#colorCvd)" 
              isAnimationActive={false} 
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
