import React, { useState, useEffect, useRef } from 'react';
import Header from './components/Header';
import MetricsBar from './components/MetricsBar';
import QuantCockpit from './components/QuantCockpit';
import FootprintChart from './components/FootprintChart';
import CvdChart from './components/CvdChart';
import DepthLadder from './components/DepthLadder';
import ExecutionPanel from './components/ExecutionPanel';
import BotConfigPanel from './components/BotConfigPanel';
import VpinChart from './components/VpinChart';
import AccountPanel from './components/AccountPanel';
import TelemetryView from './components/TelemetryView';

export default function App() {
  const [telemetry, setTelemetry] = useState({
    orderbooks: {},
    vpin: {},
    mlofi: {},
    cvd: {},
    footprint_bars: [],
    execution: {},
    open_orders: [],
    risk: {},
    connections: {},
    bot_active: false,
    equity_pnl: {},
    signal_monitor: {},
    active_position: {},
    active_order: {},
    recent_trades: [],
    risk_guard: {},
    exchange_health: {},
  });

  const [activeTab, setActiveTab] = useState('cockpit');
  const wsRef = useRef(null);

  useEffect(() => {
    // Initial state fetch
    fetch('http://localhost:8000/api/state')
      .then(res => res.json())
      .then(data => setTelemetry(prev => ({ ...prev, ...data })))
      .catch(err => console.log('Backend starting up...', err));

    const connectWs = () => {
      const wsUrl = `ws://${window.location.hostname}:8000/ws/telemetry`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'TELEMETRY_UPDATE') {
            setTelemetry(prev => ({
              ...prev,
              orderbooks: msg.orderbooks || prev.orderbooks,
              vpin: msg.vpin || prev.vpin,
              mlofi: msg.mlofi || prev.mlofi,
              cvd: msg.cvd || prev.cvd,
              footprint_bars: msg.footprint_bars || prev.footprint_bars,
              execution: msg.execution || prev.execution,
              open_orders: msg.open_orders || prev.open_orders,
              risk: msg.risk || prev.risk,
              connections: msg.connections || prev.connections,
              bot_active: msg.bot_active !== undefined ? msg.bot_active : prev.bot_active,
              equity_pnl: msg.equity_pnl || prev.equity_pnl,
              signal_monitor: msg.signal_monitor || prev.signal_monitor,
              active_position: msg.active_position || prev.active_position,
              active_order: msg.active_order || prev.active_order,
              recent_trades: msg.recent_trades || prev.recent_trades,
              risk_guard: msg.risk_guard || prev.risk_guard,
              exchange_health: msg.exchange_health || prev.exchange_health,
            }));
          }
        } catch (e) {
          console.error('Failed to parse telemetry', e);
        }
      };

      ws.onclose = () => setTimeout(connectWs, 2000);
    };

    connectWs();
    return () => { if (wsRef.current) wsRef.current.close(); };
  }, []);

  const handlePlaceOrder = async (orderPayload) => {
    const res = await fetch('http://localhost:8000/api/order', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(orderPayload),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to place order');
    }
    return await res.json();
  };

  const handleCancelOrder = async (orderIndex) => {
    await fetch(`http://localhost:8000/api/order/cancel/${orderIndex}`, { method: 'POST' });
  };

  const handleCancelAll = async () => {
    await fetch('http://localhost:8000/api/order/cancel-all', { method: 'POST' });
  };

  const handleToggleKillSwitch = async (active) => {
    await fetch('http://localhost:8000/api/kill-switch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active, reason: active ? 'Manual User Engaged' : 'Manual Reset' }),
    });
  };

  const handleToggleBot = async (active) => {
    await fetch('http://localhost:8000/api/bot/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active })
    });
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Header
        connections={telemetry.connections}
        risk={telemetry.risk}
        onToggleKillSwitch={handleToggleKillSwitch}
      />

      {/* Primary Navigation Tabs */}
      <div style={{ padding: '0 24px', display: 'flex', gap: '12px', marginTop: '16px', overflowX: 'auto' }}>
        <button
          className={`btn ${activeTab === 'cockpit' ? 'btn-bull' : 'btn-subtle'}`}
          onClick={() => setActiveTab('cockpit')}
          style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
        >
          ⚡ Quant Cockpit (5-Panel Monitor)
        </button>
        <button
          className={`btn ${activeTab === 'footprint' ? 'btn-bull' : 'btn-subtle'}`}
          onClick={() => setActiveTab('footprint')}
        >
          Order Flow & Footprint
        </button>
        <button
          className={`btn ${activeTab === 'telemetry' ? 'btn-bull' : 'btn-subtle'}`}
          onClick={() => setActiveTab('telemetry')}
        >
          Telemetry & Logs
        </button>
        <button
          className={`btn ${activeTab === 'analytics' ? 'btn-bull' : 'btn-subtle'}`}
          onClick={() => setActiveTab('analytics')}
        >
          VPIN & Bot Config
        </button>
        <button
          className={`btn ${activeTab === 'account' ? 'btn-bull' : 'btn-subtle'}`}
          onClick={() => setActiveTab('account')}
        >
          Account & History
        </button>
      </div>

      <MetricsBar
        orderbooks={telemetry.orderbooks}
        vpin={telemetry.vpin}
        mlofi={telemetry.mlofi}
        cvd={telemetry.cvd}
      />

      {/* Tab 1: Quant Cockpit (5-Panel Real-Time Telemetry Monitor) */}
      {activeTab === 'cockpit' && (
        <QuantCockpit
          telemetry={telemetry}
          onCancelOrder={handleCancelOrder}
          onToggleKillSwitch={handleToggleKillSwitch}
        />
      )}

      {/* Tab 2: Footprint & Depth Ladder */}
      {activeTab === 'footprint' && (
        <main className="workspace-grid" style={{ padding: '0 24px 24px' }}>
          <section style={{ display: 'flex', flexDirection: 'column', gap: '16px', minWidth: 0 }}>
            <FootprintChart bars={telemetry.footprint_bars} />
            <CvdChart cvd={telemetry.cvd} />
          </section>

          <aside style={{ display: 'flex', flexDirection: 'column', gap: '16px', minWidth: 0 }}>
            <DepthLadder orderbooks={telemetry.orderbooks} />
            <ExecutionPanel
              execution={telemetry.execution}
              openOrders={telemetry.open_orders}
              onPlaceOrder={handlePlaceOrder}
              onCancelOrder={handleCancelOrder}
              onCancelAll={handleCancelAll}
              risk={telemetry.risk}
              botActive={telemetry.bot_active}
            />
          </aside>
        </main>
      )}

      {/* Tab 3: Detailed Telemetry Logs */}
      {activeTab === 'telemetry' && (
        <main style={{ padding: '0 24px 24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <TelemetryView />
        </main>
      )}

      {/* Tab 4: VPIN Analytics & Bot Controls */}
      {activeTab === 'analytics' && (
        <main style={{ padding: '0 24px 24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <VpinChart />
          <BotConfigPanel botActive={telemetry.bot_active} onToggleBot={handleToggleBot} />
        </main>
      )}

      {/* Tab 5: Account & Settlement */}
      {activeTab === 'account' && (
        <main style={{ padding: '0 24px 24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <AccountPanel execution={telemetry.execution} />
        </main>
      )}
    </div>
  );
}
