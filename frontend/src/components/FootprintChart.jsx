import React, { useRef, useEffect, useState, useMemo } from 'react';
import { BarChart3, ZoomIn, ZoomOut, Layers, ArrowUpRight, ArrowDownRight } from 'lucide-react';

/**
 * FINAL_FIX #3: Institutional Global Price Grid Footprint Chart
 * - Unified vertical Price Y-Axis (aligned rows across all bars)
 * - Time-series X-Axis (oldest on left, newest on right)
 * - Sub-second aggressor trade volume clusters: Sell Vol x Buy Vol
 * - Relative heatmap intensity normalized per bar
 * - Point of Control (POC) high-volume nodes
 * - Delta, Total Volume, and Time timestamps at bottom
 * - Auto-scroll and zoom controls
 */
const FootprintChart = React.memo(function FootprintChart({ bars = [] }) {
  const [zoomLevel, setZoomLevel] = useState(1.0);
  const scrollContainerRef = useRef(null);

  // Limit to max 20 latest bars
  const visibleBars = useMemo(() => {
    return bars.slice(-20);
  }, [bars]);

  // A. Hitung global price range dari SEMUA visible bars
  const { priceGrid, processedBars } = useMemo(() => {
    if (!visibleBars || visibleBars.length === 0) {
      return { priceGrid: [], processedBars: [] };
    }

    let allPrices = [];
    visibleBars.forEach((bar) => {
      if (bar.open) allPrices.push(bar.open);
      if (bar.high) allPrices.push(bar.high);
      if (bar.low) allPrices.push(bar.low);
      if (bar.close) allPrices.push(bar.close);
      (bar.levels || []).forEach((lvl) => {
        if (lvl.price) allPrices.push(lvl.price);
      });
    });

    if (allPrices.length === 0) {
      return { priceGrid: [], processedBars: [] };
    }

    const minP = Math.min(...allPrices);
    const maxP = Math.max(...allPrices);
    const latestBar = visibleBars[visibleBars.length - 1];
    const centerPrice = Math.round(latestBar.close || (minP + maxP) / 2);

    // Uniform price grid with 1.0 tick size, bounded to max 30 levels centered around current price
    let startPrice, endPrice;
    if (maxP - minP <= 30) {
      startPrice = Math.ceil(maxP);
      endPrice = Math.floor(minP);
    } else {
      startPrice = centerPrice + 15;
      endPrice = centerPrice - 15;
    }

    const grid = [];
    for (let p = startPrice; p >= endPrice; p -= 1.0) {
      grid.push(p);
    }

    // B. Buat lookup map per bar: price -> {buy_vol, sell_vol, delta} & hitung POC
    const pBars = visibleBars.map((bar) => {
      const priceMap = new Map();
      let maxVolInBar = 0.01;
      let pocPrice = null;
      let maxPocVol = 0.0;

      (bar.levels || []).forEach((lvl) => {
        const roundedPrice = Math.round(lvl.price);
        const existing = priceMap.get(roundedPrice) || { buy_vol: 0, sell_vol: 0, delta: 0 };
        const newBuy = existing.buy_vol + lvl.buy_vol;
        const newSell = existing.sell_vol + lvl.sell_vol;
        const newDelta = newBuy - newSell;
        priceMap.set(roundedPrice, {
          buy_vol: newBuy,
          sell_vol: newSell,
          delta: newDelta,
        });

        const totVol = newBuy + newSell;
        if (totVol > maxVolInBar) {
          maxVolInBar = totVol;
        }
        if (totVol > maxPocVol) {
          maxPocVol = totVol;
          pocPrice = roundedPrice;
        }
      });

      return {
        ...bar,
        priceMap,
        maxVolInBar,
        pocPrice,
      };
    });

    return { priceGrid: grid, processedBars: pBars };
  }, [visibleBars]);

  // G. Auto-scroll to latest candle on right when new bar or trade arrives
  useEffect(() => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollLeft = scrollContainerRef.current.scrollWidth;
    }
  }, [processedBars]);

  const cellWidth = Math.round(115 * zoomLevel);
  const cellHeight = Math.round(22 * zoomLevel);
  const fontSize = Math.max(9, Math.round(10 * zoomLevel));

  return (
    <div className="glass-panel footprint-container" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {/* Chart Header */}
      <div className="chart-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <BarChart3 size={18} color="var(--accent-cyan)" />
          <h2 style={{ fontSize: '14px', fontWeight: 700, margin: 0, letterSpacing: '0.2px' }}>
            Footprint Chart (Global Price × Time Grid)
          </h2>
          <span style={{ fontSize: '11px', color: 'var(--text-dim)', marginLeft: '6px' }}>
            1.0 Tick Resolution · 5s Clustered
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {/* Legend */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '11px', color: 'var(--text-muted)' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ width: '8px', height: '8px', background: 'var(--accent-bear)', borderRadius: '2px' }} />
              Sell Taker (Bid)
            </span>
            <span>×</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ width: '8px', height: '8px', background: 'var(--accent-bull)', borderRadius: '2px' }} />
              Buy Taker (Ask)
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ width: '8px', height: '8px', border: '1px solid #f59e0b', background: 'rgba(245, 158, 11, 0.3)', borderRadius: '2px' }} />
              POC Node
            </span>
          </div>

          {/* Zoom Buttons */}
          <div style={{ display: 'flex', gap: '4px' }}>
            <button
              className="btn btn-subtle"
              style={{ padding: '4px 8px' }}
              onClick={() => setZoomLevel((z) => Math.max(0.75, z - 0.1))}
              title="Zoom Out"
            >
              <ZoomOut size={13} />
            </button>
            <button
              className="btn btn-subtle"
              style={{ padding: '4px 8px' }}
              onClick={() => setZoomLevel((z) => Math.min(1.35, z + 0.1))}
              title="Zoom In"
            >
              <ZoomIn size={13} />
            </button>
          </div>
        </div>
      </div>

      {/* Main Grid View */}
      {processedBars.length === 0 || priceGrid.length === 0 ? (
        <div style={{ padding: '48px 0', textAlign: 'center', color: 'var(--text-dim)', fontSize: '13px' }}>
          Waiting for live sub-second order flow trades...
        </div>
      ) : (
        <div
          style={{
            display: 'flex',
            border: '1px solid var(--border-subtle)',
            borderRadius: '8px',
            background: 'rgba(10, 13, 20, 0.8)',
            overflow: 'hidden',
          }}
        >
          {/* Kolom 1 (Fixed Y-Axis): Price Labels */}
          <div
            style={{
              width: '75px',
              minWidth: '75px',
              borderRight: '1px solid var(--border-subtle)',
              background: 'rgba(15, 20, 32, 0.95)',
              display: 'flex',
              flexDirection: 'column',
              zIndex: 3,
            }}
          >
            {/* Header placeholder */}
            <div
              style={{
                height: '42px',
                borderBottom: '1px solid var(--border-subtle)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '11px',
                fontWeight: 700,
                color: 'var(--text-muted)',
              }}
            >
              PRICE
            </div>

            {/* Price Levels List */}
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {priceGrid.map((price) => (
                <div
                  key={price}
                  className="mono"
                  style={{
                    height: `${cellHeight}px`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'flex-end',
                    paddingRight: '8px',
                    fontSize: `${fontSize}px`,
                    color: 'var(--text-muted)',
                    borderBottom: '1px solid rgba(255, 255, 255, 0.03)',
                  }}
                >
                  ${price.toLocaleString()}
                </div>
              ))}
            </div>

            {/* Bottom Summary Labels */}
            <div
              style={{
                borderTop: '1px solid var(--border-subtle)',
                display: 'flex',
                flexDirection: 'column',
                background: 'rgba(15, 20, 32, 0.98)',
              }}
            >
              <div
                style={{
                  height: '24px',
                  display: 'flex',
                  alignItems: 'center',
                  paddingLeft: '8px',
                  fontSize: '10px',
                  fontWeight: 700,
                  color: 'var(--text-dim)',
                  borderBottom: '1px solid rgba(255, 255, 255, 0.03)',
                }}
              >
                DELTA
              </div>
              <div
                style={{
                  height: '24px',
                  display: 'flex',
                  alignItems: 'center',
                  paddingLeft: '8px',
                  fontSize: '10px',
                  fontWeight: 700,
                  color: 'var(--text-dim)',
                  borderBottom: '1px solid rgba(255, 255, 255, 0.03)',
                }}
              >
                VOLUME
              </div>
              <div
                style={{
                  height: '24px',
                  display: 'flex',
                  alignItems: 'center',
                  paddingLeft: '8px',
                  fontSize: '10px',
                  fontWeight: 700,
                  color: 'var(--text-dim)',
                }}
              >
                TIME
              </div>
            </div>
          </div>

          {/* Kolom 2-N (Scrollable Horizontal Grid): Time Bars */}
          <div
            ref={scrollContainerRef}
            style={{
              flex: 1,
              overflowX: 'auto',
              overflowY: 'hidden',
              display: 'flex',
            }}
          >
            {processedBars.map((bar) => {
              const isBullish = bar.close >= bar.open;
              const formattedTime = bar.start_time
                ? new Date(bar.start_time * 1000).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                  })
                : '-';

              return (
                <div
                  key={bar.bar_id}
                  style={{
                    width: `${cellWidth}px`,
                    minWidth: `${cellWidth}px`,
                    borderRight: '1px solid rgba(255, 255, 255, 0.05)',
                    display: 'flex',
                    flexDirection: 'column',
                  }}
                >
                  {/* Bar Header (OHLC summary) */}
                  <div
                    style={{
                      height: '42px',
                      padding: '4px 6px',
                      background: isBullish ? 'rgba(16, 185, 129, 0.12)' : 'rgba(244, 63, 94, 0.12)',
                      borderBottom: '1px solid var(--border-subtle)',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'center',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '10px' }}>
                      <span className="mono" style={{ fontWeight: 700, color: isBullish ? 'var(--accent-bull)' : 'var(--accent-bear)' }}>
                        #{bar.bar_id}
                      </span>
                      <span className="mono" style={{ fontWeight: 700, color: 'var(--text-main)' }}>
                        ${bar.close?.toFixed(1)}
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '9px', color: 'var(--text-dim)' }}>
                      <span>O: {bar.open?.toFixed(0)}</span>
                      <span>H: {bar.high?.toFixed(0)}</span>
                      <span>L: {bar.low?.toFixed(0)}</span>
                    </div>
                  </div>

                  {/* Footprint Rows for each price level */}
                  <div style={{ display: 'flex', flexDirection: 'column' }}>
                    {priceGrid.map((price) => {
                      const lvl = bar.priceMap.get(price);
                      const isPoc = price === bar.pocPrice;

                      if (!lvl) {
                        // Empty cell where no trade occurred at this price level
                        return (
                          <div
                            key={price}
                            style={{
                              height: `${cellHeight}px`,
                              borderBottom: '1px solid rgba(255, 255, 255, 0.02)',
                              background: 'rgba(255, 255, 255, 0.005)',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              color: 'rgba(255, 255, 255, 0.08)',
                              fontSize: '8px',
                            }}
                          >
                            ·
                          </div>
                        );
                      }

                      const buy = lvl.buy_vol || 0;
                      const sell = lvl.sell_vol || 0;
                      const totalVol = buy + sell;
                      const buyDominant = buy > sell;
                      const sellDominant = sell > buy;

                      // Heatmap intensity: normalized by maxVolInBar, max 0.7 opacity
                      const intensity = Math.min(0.7, (totalVol / bar.maxVolInBar) * 0.7);
                      const bg = isPoc
                        ? 'rgba(245, 158, 11, 0.22)'
                        : buyDominant
                        ? `rgba(16, 185, 129, ${0.12 + intensity})`
                        : sellDominant
                        ? `rgba(244, 63, 94, ${0.12 + intensity})`
                        : 'rgba(255, 255, 255, 0.05)';

                      return (
                        <div
                          key={price}
                          className="mono"
                          style={{
                            height: `${cellHeight}px`,
                            borderBottom: '1px solid rgba(255, 255, 255, 0.03)',
                            border: isPoc ? '1px solid #f59e0b' : undefined,
                            background: bg,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            padding: '0 4px',
                            fontSize: `${fontSize}px`,
                            fontWeight: isPoc ? 700 : 500,
                            color: '#fff',
                            transition: 'background 0.2s ease',
                          }}
                          title={`Price $${price}: Sell ${sell.toFixed(2)} BTC × Buy ${buy.toFixed(2)} BTC (Delta: ${(buy - sell).toFixed(2)})`}
                        >
                          {/* Sell volume (red/neutral) */}
                          <span style={{ color: sellDominant ? '#fff' : 'rgba(255, 255, 255, 0.65)' }}>
                            {sell > 0 ? sell.toFixed(2) : '-'}
                          </span>
                          <span style={{ color: 'rgba(255, 255, 255, 0.25)', fontSize: '8px' }}>×</span>
                          {/* Buy volume (green/neutral) */}
                          <span style={{ color: buyDominant ? '#fff' : 'rgba(255, 255, 255, 0.65)' }}>
                            {buy > 0 ? buy.toFixed(2) : '-'}
                          </span>
                        </div>
                      );
                    })}
                  </div>

                  {/* Summary Rows (D, E, F): Delta, Volume, Time */}
                  <div
                    style={{
                      borderTop: '1px solid var(--border-subtle)',
                      display: 'flex',
                      flexDirection: 'column',
                      background: 'rgba(15, 20, 32, 0.95)',
                    }}
                  >
                    {/* D. Row: Delta per bar */}
                    <div
                      className="mono"
                      style={{
                        height: '24px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '10px',
                        fontWeight: 700,
                        color: bar.delta >= 0 ? 'var(--accent-bull)' : 'var(--accent-bear)',
                        borderBottom: '1px solid rgba(255, 255, 255, 0.03)',
                      }}
                    >
                      {bar.delta >= 0 ? `+${bar.delta.toFixed(2)}` : bar.delta.toFixed(2)}
                    </div>

                    {/* E. Row: Volume per bar */}
                    <div
                      className="mono"
                      style={{
                        height: '24px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '10px',
                        color: 'var(--text-main)',
                        borderBottom: '1px solid rgba(255, 255, 255, 0.03)',
                      }}
                    >
                      {bar.volume ? bar.volume.toFixed(2) : '0.00'}
                    </div>

                    {/* F. Row: Time labels (HH:MM:SS) */}
                    <div
                      className="mono"
                      style={{
                        height: '24px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '9px',
                        color: 'var(--text-dim)',
                      }}
                    >
                      {formattedTime}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
});

export default FootprintChart;
