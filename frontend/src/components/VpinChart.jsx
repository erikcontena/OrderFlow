import React, { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { Activity } from 'lucide-react';

export default function VpinChart() {
  const [data, setData] = useState([]);

  useEffect(() => {
    const fetchAnalytics = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/history/analytics');
        const history = await res.json();
        // reverse the history if it's descending so it goes from old to new left-to-right
        if (history && history.length > 0) {
          setData(history.reverse().map(item => ({
            time: new Date(item.timestamp).toLocaleTimeString(),
            vpin: item.vpin_value,
            is_toxic: item.vpin_is_toxic ? 1 : 0
          })));
        }
      } catch (e) {
        console.error("Failed to fetch analytics history", e);
      }
    };
    fetchAnalytics();
    const interval = setInterval(fetchAnalytics, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="glass-panel" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px', height: '300px' }}>
      <div className="chart-header" style={{ marginBottom: 0 }}>
        <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px' }}>
          <Activity size={18} color="#a855f7" /> VPIN Analytics History
        </h3>
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <XAxis dataKey="time" stroke="#64748b" fontSize={11} tickMargin={8} />
            <YAxis stroke="#64748b" fontSize={11} domain={[0, 1]} tickCount={5} />
            <Tooltip 
              contentStyle={{ backgroundColor: '#0f1420', borderColor: '#334155', borderRadius: '8px' }}
              itemStyle={{ color: '#f1f5f9' }}
            />
            <ReferenceLine y={0.65} stroke="#f43f5e" strokeDasharray="3 3" label={{ position: 'top', value: 'Toxicity Threshold (0.65)', fill: '#f43f5e', fontSize: 10 }} />
            <Line type="monotone" dataKey="vpin" stroke="#a855f7" strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
