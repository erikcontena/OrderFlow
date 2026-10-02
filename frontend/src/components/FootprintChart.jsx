import React, { useRef, useEffect, useState } from 'react';
import { BarChart3, Layers, ZoomIn, ZoomOut } from 'lucide-react';

export default function FootprintChart({ bars = [] }) {
  const [zoom, setZoom] = useState(1);
  const containerRef = useRef(null);

  // Auto-scroll to latest candle on right
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollLeft = containerRef.current.scrollWidth;
    }
  }, [bars]);

  return (
    <div className="glass-panel footprint-container">
      <div className="chart-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <BarChart3 size={18} color="#06b6d4" />
          <h2 style={{ fontSize: '14px', fontWeight: 700, margin: 0 }}>
            Sub-Second Footprint Chart (Bid x Ask Imbalance)
          </h2>
          <span style={{ fontSize: '11px', color: 'var(--text-dim)', marginLeft: '6px' }}>
            5s Volume Clustered
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', color: 'var(--text-muted)' }}>
            <span style={{ display: 'inline-block', width: '10px', height: '10px', background: 'rgba(16, 185, 129, 0.4)', borderRadius: '2px' }}></span>
            <span>Aggressive Buy</span>
            <span style={{ display: 'inline-block', width: '10px', height: '10px', background: 'rgba(244, 63, 94, 0.4)', borderRadius: '2px', marginLeft: '6px' }}></span>
            <span>Aggressive Sell</span>
            <span style={{ display: 'inline-block', width: '10px', height: '10px', border: '1px solid #f59e0b', borderRadius: '2px', marginLeft: '6px' }}></span>
            <span style={{ color: 'var(--accent-warning)' }}>POC (Point of Control)</span>
          </div>

          <div style={{ display: 'flex', gap: '4px' }}>
            <button 
              className="btn btn-subtle" 
              style={{ padding: '4px 8px' }} 
              onClick={() => setZoom(z => Math.max(0.7, z - 0.1))}
            >
              <ZoomOut size={12} />
            </button>
            <button 
              className="btn btn-subtle" 
              style={{ padding: '4px 8px' }} 
              onClick={() => setZoom(z => Math.min(1.4, z + 0.1))}
            >
              <ZoomIn size={12} />
            </button>
          </div>
        </div>
      </div>

      {/* Footprint candles strip */}
      <div 
        ref={containerRef}
        style={{
          display: 'flex',
          gap: '16px',
          overflowX: 'auto',
          overflowY: 'hidden',
          flex: 1,
          alignItems: 'stretch',
          paddingBottom: '8px',
          transform: `scale(${zoom})`,
          transformOrigin: 'bottom left'
        }}
      >
        {bars.length === 0 ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%', color: 'var(--text-dim)', fontSize: '13px' }}>
            Waiting for live trade ticks from Binance/Hyperliquid/Bitget/Bybit feeds...
          </div>
        ) : (
          bars.map((bar) => {
            const isBullish = bar.close >= bar.open;
            const levels = bar.levels || [];
            
            // Determine Point of Control (POC): price level with highest (buy_vol + sell_vol)
            let pocPrice = null;
            let maxLevelVol = 0;
            levels.forEach(lvl => {
              const tot = lvl.buy_vol + lvl.sell_vol;
              if (tot > maxLevelVol) {
                maxLevelVol = tot;
                pocPrice = lvl.price;
              }
            });

            return (
              <div
                key={bar.bar_id}
                style={{
                  minWidth: '130px',
                  display: 'flex',
                  flexDirection: 'column',
                  background: 'rgba(0, 0, 0, 0.25)',
                  border: `1px solid ${isBullish ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)'}`,
                  borderRadius: '8px',
                  overflow: 'hidden'
                }}
              >
                {/* Bar Header (OHLC summary) */}
                <div 
                  style={{
                    padding: '6px 8px',
                    background: isBullish ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
                    borderBottom: '1px solid var(--border-subtle)',
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontSize: '11px'
                  }}
                >
                  <span className="mono" style={{ fontWeight: 700, color: isBullish ? 'var(--accent-bull)' : 'var(--accent-bear)' }}>
                    #{bar.bar_id}
                  </span>
                  <span className="mono" style={{ color: 'var(--text-main)' }}>
                    ${bar.close.toFixed(1)}
                  </span>
                </div>

                {/* Footprint Price Levels (Bid Vol x Ask Vol) */}
                <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '2px', padding: '4px' }}>
                  {levels.slice(0, 14).map((lvl) => {
                    const isPoc = lvl.price === pocPrice;
                    const buyDominant = lvl.buy_vol > lvl.sell_vol * 1.5 && lvl.buy_vol > 0.05;
                    const sellDominant = lvl.sell_vol > lvl.buy_vol * 1.5 && lvl.sell_vol > 0.05;

                    return (
                      <div
                        key={lvl.price}
                        className="mono"
                        style={{
                          display: 'grid',
                          gridTemplateColumns: '1fr 48px 1fr',
                          alignItems: 'stretch',
                          fontSize: '10px',
                          borderRadius: '4px',
                          background: isPoc ? 'rgba(245, 158, 11, 0.12)' : 'rgba(255, 255, 255, 0.02)',
                          border: isPoc ? '1px solid #f59e0b' : '1px solid transparent',
                          position: 'relative',
                          overflow: 'hidden'
                        }}
                      >
                        {/* Sell Aggressor Heatmap (into Bid) */}
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'flex-end',
                            paddingRight: '4px',
                            background: `rgba(244, 63, 94, ${(lvl.sell_vol / (maxLevelVol || 1)) * 0.8})`,
                            color: sellDominant ? '#fff' : 'rgba(255,255,255,0.8)',
                            fontWeight: sellDominant ? 700 : 500,
                            borderRight: '1px solid rgba(0,0,0,0.2)'
                          }}
                        >
                          {lvl.sell_vol > 0 ? lvl.sell_vol.toFixed(2) : '-'}
                        </div>

                        {/* Price Tick */}
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            color: isPoc ? '#f59e0b' : 'var(--text-muted)',
                            fontSize: '9px',
                            fontWeight: isPoc ? 700 : 400,
                            background: 'rgba(0,0,0,0.2)'
                          }}
                        >
                          {lvl.price.toFixed(1)}
                        </div>

                        {/* Buy Aggressor Heatmap (into Ask) */}
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'flex-start',
                            paddingLeft: '4px',
                            background: `rgba(16, 185, 129, ${(lvl.buy_vol / (maxLevelVol || 1)) * 0.8})`,
                            color: buyDominant ? '#fff' : 'rgba(255,255,255,0.8)',
                            fontWeight: buyDominant ? 700 : 500,
                            borderLeft: '1px solid rgba(0,0,0,0.2)'
                          }}
                        >
                          {lvl.buy_vol > 0 ? lvl.buy_vol.toFixed(2) : '-'}
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Bar Footer: Delta, Volume, CVD */}
                <div
                  className="mono"
                  style={{
                    padding: '6px 8px',
                    borderTop: '1px solid var(--border-subtle)',
                    background: 'rgba(0, 0, 0, 0.4)',
                    fontSize: '10px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '2px'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-dim)' }}>Delta:</span>
                    <span style={{ color: bar.delta >= 0 ? 'var(--accent-bull)' : 'var(--accent-bear)', fontWeight: 700 }}>
                      {bar.delta >= 0 ? `+${bar.delta.toFixed(2)}` : bar.delta.toFixed(2)}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-dim)' }}>Vol:</span>
                    <span style={{ color: 'var(--text-main)' }}>{bar.volume.toFixed(2)}</span>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
