import React, { useState } from 'react';
import { Layers, ArrowUpDown } from 'lucide-react';

export default function DepthLadder({ orderbooks = {} }) {
  const venues = ['binance', 'hyperliquid', 'bitget', 'bybit', 'lighter'];
  const [selectedVenue, setSelectedVenue] = useState('binance');

  const currentBook = orderbooks[selectedVenue] || {};
  const bids = currentBook.bids || [];
  const asks = currentBook.asks || [];
  
  // Find max volume to scale depth bars
  const maxBidVol = Math.max(...bids.map(b => b[1]), 1.0);
  const maxAskVol = Math.max(...asks.map(a => a[1]), 1.0);

  return (
    <div className="glass-panel" style={{ padding: '16px', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Layers size={16} color="var(--accent-purple)" />
          <span style={{ fontSize: '14px', fontWeight: 700 }}>Cross-Venue LOB Ladder</span>
        </div>
      </div>

      {/* Venue Switcher Tabs */}
      <div style={{ display: 'flex', gap: '4px', background: 'rgba(0,0,0,0.3)', padding: '3px', borderRadius: '8px', marginBottom: '12px', flexWrap: 'wrap' }}>
        {venues.map((v) => {
          const isSelected = selectedVenue === v;
          const book = orderbooks[v] || {};
          const isSynced = book.is_synced;

          return (
            <button
              key={v}
              onClick={() => setSelectedVenue(v)}
              className="btn btn-subtle"
              style={{
                flex: 1,
                padding: '5px 8px',
                fontSize: '11px',
                background: isSelected ? 'rgba(6, 182, 212, 0.2)' : 'transparent',
                borderColor: isSelected ? 'var(--accent-cyan)' : 'transparent',
                color: isSelected ? 'var(--text-main)' : 'var(--text-dim)',
                textTransform: 'capitalize'
              }}
            >
              <span className={`status-dot ${isSynced ? 'active' : 'inactive'}`} style={{ width: '6px', height: '6px' }} />
              {v}
            </button>
          );
        })}
      </div>

      {/* Mid Price & Spread Banner */}
      <div 
        style={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          background: 'rgba(255,255,255,0.02)', 
          padding: '8px 10px', 
          borderRadius: '6px',
          border: '1px solid var(--border-subtle)',
          marginBottom: '10px',
          fontSize: '12px'
        }}
      >
        <span style={{ color: 'var(--text-muted)' }}>Mid: <strong className="mono" style={{ color: 'var(--text-main)' }}>${(currentBook.mid_price || 0).toFixed(1)}</strong></span>
        <span style={{ color: 'var(--text-muted)' }}>Spread: <strong className="mono" style={{ color: 'var(--accent-cyan)' }}>${(currentBook.spread || 0).toFixed(1)}</strong> ({(currentBook.spread_bps || 0).toFixed(2)} bps)</span>
      </div>

      {/* Depth Table */}
      <div style={{ maxHeight: '280px', overflowY: 'auto' }}>
        <table className="ladder-table mono">
          <thead>
            <tr>
              <th style={{ textAlign: 'left' }}>Price (USD)</th>
              <th>Size (BTC)</th>
              <th>Sum</th>
            </tr>
          </thead>
          <tbody>
            {/* Top Asks (reversed so lowest ask is nearest to mid) */}
            {asks.slice(0, 6).reverse().map(([price, size], idx) => {
              const depthPct = Math.min(100, (size / maxAskVol) * 100);
              return (
                <tr key={`ask-${price}`} className="ask-row">
                  <td style={{ textAlign: 'left', fontWeight: 600 }}>${price.toFixed(1)}</td>
                  <td style={{ position: 'relative' }}>
                    <div className="depth-bar-ask" style={{ position: 'absolute', inset: 0, width: `${depthPct}%`, pointerEvents: 'none' }} />
                    <span style={{ position: 'relative', zIndex: 1 }}>{size.toFixed(3)}</span>
                  </td>
                  <td>{(size).toFixed(3)}</td>
                </tr>
              );
            })}

            {/* Mid separator */}
            <tr style={{ background: 'rgba(255,255,255,0.04)', borderTop: '1px solid var(--border-subtle)', borderBottom: '1px solid var(--border-subtle)' }}>
              <td colSpan="3" style={{ textAlign: 'center', padding: '4px', fontSize: '11px', color: 'var(--accent-cyan)' }}>
                Spread: ${(currentBook.spread || 0).toFixed(1)}
              </td>
            </tr>

            {/* Top Bids (highest bid nearest to mid) */}
            {bids.slice(0, 6).map(([price, size], idx) => {
              const depthPct = Math.min(100, (size / maxBidVol) * 100);
              return (
                <tr key={`bid-${price}`} className="bid-row">
                  <td style={{ textAlign: 'left', fontWeight: 600 }}>${price.toFixed(1)}</td>
                  <td style={{ position: 'relative' }}>
                    <div className="depth-bar-bid" style={{ position: 'absolute', inset: 0, width: `${depthPct}%`, pointerEvents: 'none' }} />
                    <span style={{ position: 'relative', zIndex: 1 }}>{size.toFixed(3)}</span>
                  </td>
                  <td>{(size).toFixed(3)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
