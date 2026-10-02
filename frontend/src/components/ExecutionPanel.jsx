import React, { useState, useEffect } from 'react';
import { Send, Trash2, ShieldCheck, AlertCircle, Play, Square, Bot, TrendingUp, DollarSign, Database, RotateCcw, Clock } from 'lucide-react';

export default function ExecutionPanel({ execution = {}, openOrders = [], onCancelOrder, onCancelAll, risk = {}, botActive }) {
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [leverage, setLeverage] = useState(1);
  
  const updateLeverage = async (newVal) => {
    setLeverage(newVal);
    try {
      await fetch('http://localhost:8000/api/leverage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ leverage: parseFloat(newVal) }),
      });
    } catch (err) {
      console.error("Failed to update leverage", err);
    }
  };

  const isPaused = risk?.passive_quoting_paused;
  const isKillSwitch = risk?.kill_switch_active;
  const networkMode = execution.mode || 'TESTNET';
  
  // Optimistic UI state
  const [localMode, setLocalMode] = useState(null);
  const displayMode = localMode || networkMode;

  const switchMode = async (mode) => {
    setLocalMode(mode.toUpperCase());
    try {
      await fetch('http://localhost:8000/api/execution/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
      });
    } catch (err) {
      console.error("Failed to switch mode", err);
      setLocalMode(null); // Revert on failure
    }
  };

  const toggleBot = async () => {
    setSubmitting(true);
    try {
      const response = await fetch('http://localhost:8000/api/bot/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: !botActive }),
      });
      // State is updated optimistically or via websocket, so no local setBotActive needed
    } catch (err) {
      console.error("Failed to toggle bot", err);
    } finally {
      setSubmitting(false);
    }
  };

  const [editingAccount, setEditingAccount] = useState(false);
  const [accountInput, setAccountInput] = useState('');
  const [bottomTab, setBottomTab] = useState('orders'); // 'orders' | 'history' | 'logs'
  const [dbOrders, setDbOrders] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const fetchDbHistory = async () => {
    setLoadingHistory(true);
    try {
      const res = await fetch('http://localhost:8000/api/history/orders?limit=25');
      if (res.ok) {
        const data = await res.json();
        setDbOrders(data);
      }
    } catch (e) {
      console.error("Failed to fetch DB history", e);
    } finally {
      setLoadingHistory(false);
    }
  };

  useEffect(() => {
    if (bottomTab === 'history') {
      fetchDbHistory();
      const interval = setInterval(fetchDbHistory, 3000);
      return () => clearInterval(interval);
    }
  }, [bottomTab]);

  const saveAccount = async () => {
    if (!accountInput) return;
    try {
      await fetch('http://localhost:8000/api/execution/account', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account: accountInput.trim() }),
      });
      setEditingAccount(false);
    } catch (err) {
      console.error("Failed to update account", err);
    }
  };

  const togglePaper = async (paperVal) => {
    try {
      await fetch('http://localhost:8000/api/execution/paper', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paper: paperVal }),
      });
    } catch (err) {
      console.error("Failed to set paper trading", err);
    }
  };

  const equity = execution.equity_usd !== undefined ? execution.equity_usd : 10000;
  const position = execution.position || 0.0;
  const pnl = execution.unrealized_pnl || 0.0;
  const isPaper = execution.is_simulation;

  return (
    <div className="glass-panel" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Bot size={18} color="var(--accent-glow)" />
          <span style={{ fontSize: '14px', fontWeight: 700 }}>Autonomous Bot Controller</span>
        </div>
        <div style={{ flexShrink: 0, marginLeft: 'auto', paddingLeft: '8px' }}>
          <button
            onClick={toggleBot}
            disabled={submitting || isKillSwitch}
            className={`btn ${botActive ? 'btn-bear' : 'btn-bull'}`}
            style={{ padding: '6px 12px', fontSize: '12px' }}
          >
            {botActive ? (
              <><Square size={12} /> STOP BOT</>
            ) : (
              <><Play size={12} /> START BOT</>
            )}
          </button>
        </div>
      </div>

      {/* Adverse Selection / STP Alert Banner */}
      {isPaused && (
        <div style={{ background: 'rgba(244,63,94,0.15)', border: '1px solid var(--accent-bear)', borderRadius: '6px', padding: '6px 10px', fontSize: '11px', color: '#ff6b81', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <AlertCircle size={14} />
          <span>VPIN Toxic Spike active! Bot passive orders paused.</span>
        </div>
      )}

      {/* Leverage Slider */}
      <div className="glass-panel" style={{ padding: '10px', background: 'var(--bg-panel-dark)', marginBottom: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 600 }}>Cross Leverage</span>
          <span className="mono" style={{ fontSize: '12px', fontWeight: 700, color: 'var(--accent-glow)' }}>{leverage}x</span>
        </div>
        <input 
          type="range" 
          min="1" 
          max="50" 
          value={leverage} 
          onChange={(e) => updateLeverage(e.target.value)}
          style={{ width: '100%', cursor: 'pointer' }}
        />
      </div>

      {/* Metrics have been moved to Account Panel */}

      {botActive && (
        <div style={{ fontSize: '11px', color: 'var(--accent-glow)', textAlign: 'center', animation: 'pulse 2s infinite' }}>
          ● Bot is actively monitoring OrderFlow...
        </div>
      )}

      {/* Interactive Segmented Tabs: Open Orders | DB History | Live Logs */}
      <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '10px' }}>
        <div style={{ display: 'flex', gap: '4px', marginBottom: '8px', background: 'rgba(0,0,0,0.35)', padding: '3px', borderRadius: '6px' }}>
          <button
            onClick={() => setBottomTab('orders')}
            className="mono"
            style={{
              flex: 1,
              padding: '4px 6px',
              fontSize: '11px',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              background: bottomTab === 'orders' ? 'var(--bg-card)' : 'transparent',
              color: bottomTab === 'orders' ? 'var(--text-main)' : 'var(--text-dim)',
              fontWeight: bottomTab === 'orders' ? 600 : 400,
            }}
          >
            Open ({openOrders.length})
          </button>
          <button
            onClick={() => setBottomTab('history')}
            className="mono"
            style={{
              flex: 1,
              padding: '4px 6px',
              fontSize: '11px',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '4px',
              background: bottomTab === 'history' ? 'var(--bg-card)' : 'transparent',
              color: bottomTab === 'history' ? '#00e5ff' : 'var(--text-dim)',
              fontWeight: bottomTab === 'history' ? 600 : 400,
            }}
          >
            <Database size={11} /> DB History
          </button>
          <button
            onClick={() => setBottomTab('logs')}
            className="mono"
            style={{
              flex: 1,
              padding: '4px 6px',
              fontSize: '11px',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              background: bottomTab === 'logs' ? 'var(--bg-card)' : 'transparent',
              color: bottomTab === 'logs' ? 'var(--text-main)' : 'var(--text-dim)',
              fontWeight: bottomTab === 'logs' ? 600 : 400,
            }}
          >
            Logs
          </button>
        </div>

        {/* Tab 1: Open Orders */}
        {bottomTab === 'orders' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '4px' }}>
              {openOrders.length > 0 && (
                <button
                  onClick={onCancelAll}
                  className="btn btn-subtle"
                  style={{ fontSize: '10px', padding: '2px 6px', color: 'var(--accent-bear)' }}
                >
                  <Trash2 size={11} /> Cancel All
                </button>
              )}
            </div>
            <div style={{ maxHeight: '140px', overflowY: 'auto' }}>
              {openOrders.length === 0 ? (
                <div style={{ fontSize: '11px', color: 'var(--text-dim)', textAlign: 'center', padding: '14px' }}>
                  No active resting orders in book.
                </div>
              ) : (
                <table className="ladder-table mono" style={{ fontSize: '11px', width: '100%' }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: 'left' }}>Index</th>
                      <th>Side</th>
                      <th>Price</th>
                      <th>Amt</th>
                      <th style={{ textAlign: 'right' }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {openOrders.map((ord) => (
                      <tr key={ord.client_order_index}>
                        <td style={{ textAlign: 'left', color: 'var(--text-dim)' }}>#{ord.client_order_index}</td>
                        <td style={{ color: ord.side === 'BUY' ? 'var(--accent-bull)' : 'var(--accent-bear)', fontWeight: 600, textAlign: 'center' }}>{ord.side}</td>
                        <td style={{ textAlign: 'center' }}>${ord.price.toFixed(1)}</td>
                        <td style={{ textAlign: 'center' }}>{ord.amount.toFixed(3)}</td>
                        <td style={{ textAlign: 'right' }}>
                          <button onClick={() => onCancelOrder(ord.client_order_index)} style={{ background: 'none', border: 'none', color: 'var(--accent-bear)', cursor: 'pointer' }} title="Cancel Order">
                            <Trash2 size={12} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}

        {/* Tab 2: PostgreSQL DB History */}
        {bottomTab === 'history' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
              <span style={{ fontSize: '10px', color: 'var(--text-dim)' }}>
                PostgreSQL Real-time Persistence
              </span>
              <button
                onClick={fetchDbHistory}
                className="btn btn-subtle"
                style={{ fontSize: '10px', padding: '2px 6px', display: 'flex', alignItems: 'center', gap: '4px' }}
                title="Refresh DB History"
              >
                <RotateCcw size={10} className={loadingHistory ? 'spin' : ''} /> Refresh
              </button>
            </div>
            <div style={{ maxHeight: '140px', overflowY: 'auto' }}>
              {dbOrders.length === 0 ? (
                <div style={{ fontSize: '11px', color: 'var(--text-dim)', textAlign: 'center', padding: '14px' }}>
                  No historical DB orders found.
                </div>
              ) : (
                <table className="ladder-table mono" style={{ fontSize: '10px', width: '100%' }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: 'left' }}>Idx</th>
                      <th>Side</th>
                      <th>Price</th>
                      <th>Amt</th>
                      <th style={{ textAlign: 'right' }}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dbOrders.map((ord) => {
                      let statusColor = 'var(--text-dim)';
                      if (ord.status === 'FILLED') statusColor = 'var(--accent-bull)';
                      else if (ord.status === 'OPEN') statusColor = '#00e5ff';
                      else if (ord.status === 'REJECTED') statusColor = '#ff6b81';
                      else if (ord.status === 'CANCELED') statusColor = 'var(--text-muted)';
                      
                      return (
                        <tr key={ord.id}>
                          <td style={{ textAlign: 'left', color: 'var(--text-dim)' }}>#{ord.client_order_index}</td>
                          <td style={{ color: ord.side === 'BUY' ? 'var(--accent-bull)' : 'var(--accent-bear)', fontWeight: 600, textAlign: 'center' }}>{ord.side}</td>
                          <td style={{ textAlign: 'center' }}>${ord.price.toFixed(1)}</td>
                          <td style={{ textAlign: 'center' }}>{ord.amount.toFixed(3)}</td>
                          <td style={{ textAlign: 'right', fontWeight: 600, color: statusColor }}>{ord.status}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}

        {/* Tab 3: Execution Log */}
        {bottomTab === 'logs' && (
          <div className="mono glass-panel" style={{ maxHeight: '140px', overflowY: 'auto', padding: '8px', fontSize: '10px', background: 'var(--bg-panel-dark)' }}>
            {execution.bot_logs && execution.bot_logs.length > 0 ? (
              execution.bot_logs.map((log, i) => {
                let color = 'var(--text-dim)';
                if (log.level === 'buy') color = 'var(--accent-bull)';
                else if (log.level === 'sell') color = 'var(--accent-bear)';
                else if (log.level === 'warn') color = 'var(--accent-glow)';
                else if (log.level === 'error') color = '#ff6b81';
                
                const date = new Date(log.timestamp * 1000);
                const timeStr = isNaN(date.getTime()) ? '' : `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}:${date.getSeconds().toString().padStart(2, '0')}`;
                
                return (
                  <div key={i} style={{ marginBottom: '4px', display: 'flex', gap: '6px' }}>
                    <span style={{ color: 'var(--text-muted)' }}>[{timeStr}]</span>
                    <span style={{ color }}>{log.message}</span>
                  </div>
                );
              })
            ) : (
              <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '10px' }}>Waiting for bot activity...</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
