import React, { useState, useEffect, useRef } from 'react';
import Header from './components/Header';
import MetricsBar from './components/MetricsBar';
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
  });

  const [activeTab, setActiveTab] = useState('dashboard');
  const wsRef = useRef(null);

  useEffect(() => {
    fetch('http://localhost:8000/api/state')
      .then(res => res.json())
      .then(data => setTelemetry(data))
      .catch(err => console.log('Backend starting up...'));

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

      <div style={{ padding: '0 24px', display: 'flex', gap: '16px', marginTop: '16px' }}>
        <button className={`btn ${activeTab === 'dashboard' ? 'btn-bull' : 'btn-subtle'}`} onClick={() => setActiveTab('dashboard')}>
          Live Dashboard
        </button>
        <button className={`btn ${activeTab === 'telemetry' ? 'btn-bull' : 'btn-subtle'}`} onClick={() => setActiveTab('telemetry')}>
          Signals & PnL Curve
        </button>
        <button className={`btn ${activeTab === 'analytics' ? 'btn-bull' : 'btn-subtle'}`} onClick={() => setActiveTab('analytics')}>
          Analytics & Settings
        </button>
        <button className={`btn ${activeTab === 'account' ? 'btn-bull' : 'btn-subtle'}`} onClick={() => setActiveTab('account')}>
          Account & History
        </button>
      </div>

      <MetricsBar
        orderbooks={telemetry.orderbooks}
        vpin={telemetry.vpin}
        mlofi={telemetry.mlofi}
        cvd={telemetry.cvd}
      />

      {activeTab === 'dashboard' && (
        <main className="workspace-grid">
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

      {activeTab === 'telemetry' && (
        <main style={{ padding: '0 24px 24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <TelemetryView />
        </main>
      )}

      {activeTab === 'analytics' && (
        <main style={{ padding: '0 24px 24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <VpinChart />
          <BotConfigPanel botActive={telemetry.bot_active} onToggleBot={handleToggleBot} />
        </main>
      )}

      {activeTab === 'account' && (
        <main style={{ padding: '0 24px 24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <AccountPanel execution={telemetry.execution} />
        </main>
      )}
    </div>
  );
}
