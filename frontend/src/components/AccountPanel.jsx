import React, { useState, useEffect } from 'react';
import { User, Wallet, History, Radio, Server, CheckCircle2, XCircle } from 'lucide-react';

export default function AccountPanel({ execution }) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchHistory();
    const interval = setInterval(fetchHistory, 10000);
    return () => clearInterval(interval);
  }, []);

  const fetchHistory = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/history/trades');
      const data = await res.json();
      setHistory(data);
    } catch (err) {
      console.error("Failed to load history", err);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '16px' }}>
        {/* Connection Status Card */}
        <div className="glass-panel" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', color: 'var(--text-muted)', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            <Server size={14} /> Connection Info
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: 'var(--text-dim)' }}>Network Mode</span>
              <div style={{ display: 'flex', gap: '4px', background: 'rgba(0,0,0,0.3)', padding: '2px', borderRadius: '6px' }}>
                <button 
                  className="btn" 
                  style={{ 
                    padding: '4px 8px', fontSize: '11px', 
                    background: execution.mode === 'TESTNET' ? 'var(--accent-cyan)' : 'transparent',
                    color: execution.mode === 'TESTNET' ? '#000' : 'var(--text-muted)'
                  }}
                  onClick={() => {
                    const savedIdx = localStorage.getItem('account_index_testnet');
                    fetch('http://localhost:8000/api/execution/mode', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ mode: 'testnet' }) }).then(() => {
                      if (savedIdx) fetch('http://localhost:8000/api/execution/account', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ account: savedIdx }) });
                    });
                  }}
                >
                  TESTNET
                </button>
                <button 
                  className="btn" 
                  style={{ 
                    padding: '4px 8px', fontSize: '11px', 
                    background: execution.mode === 'MAINNET' ? 'var(--accent-purple)' : 'transparent',
                    color: execution.mode === 'MAINNET' ? '#fff' : 'var(--text-muted)'
                  }}
                  onClick={() => {
                    fetch('http://localhost:8000/api/execution/mode', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ mode: 'mainnet' }) });
                  }}
                >
                  MAINNET
                </button>
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-dim)' }}>Sync Status</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontWeight: 600, color: execution.is_account_synced ? 'var(--accent-bull)' : 'var(--accent-warning)' }}>
                {execution.is_account_synced ? <><CheckCircle2 size={14}/> Synced</> : <><XCircle size={14}/> Not Synced</>}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: 'var(--text-dim)' }}>Trading Mode</span>
              <div style={{ display: 'flex', gap: '4px' }}>
                <button 
                  className={`btn ${execution.is_simulation ? 'btn-subtle' : 'btn-bear'}`}
                  style={{ padding: '4px 8px', fontSize: '11px', opacity: execution.is_simulation ? 0.6 : 1 }}
                  onClick={() => {
                    if(window.confirm('WARNING: Enabling Live Execution uses real funds. Proceed?')) {
                      fetch('http://localhost:8000/api/execution/paper', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ paper: false }) });
                    }
                  }}
                >
                  LIVE
                </button>
                <button 
                  className={`btn ${execution.is_simulation ? 'btn-bull' : 'btn-subtle'}`}
                  style={{ padding: '4px 8px', fontSize: '11px' }}
                  onClick={() => {
                    fetch('http://localhost:8000/api/execution/paper', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ paper: true }) });
                  }}
                >
                  PAPER
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Account Details Card */}
        <div className="glass-panel" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', color: 'var(--text-muted)', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            <User size={14} /> Account Details
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: 'var(--text-dim)' }}>Account Index</span>
              <div style={{ display: 'flex', gap: '8px' }}>
                <input 
                  key={`acc_${execution.mode}_${execution.account_index}`}
                  type="text" 
                  defaultValue={execution.account_index}
                  onBlur={(e) => {
                    if(e.target.value !== String(execution.account_index)) {
                      fetch('http://localhost:8000/api/execution/account', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ account: e.target.value }) });
                    }
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      fetch('http://localhost:8000/api/execution/account', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ account: e.target.value }) });
                      e.target.blur();
                    }
                  }}
                  className="mono"
                  style={{ width: '80px', padding: '4px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border-subtle)', color: 'white', borderRadius: '4px', textAlign: 'right' }}
                />
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: 'var(--text-dim)' }}>API Key Index</span>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <input
                  key={`api_${execution.mode}_${execution.api_key_index}`}
                  type="number"
                  defaultValue={execution.api_key_index}
                  onBlur={(e) => {
                    if(e.target.value !== String(execution.api_key_index)) {
                      fetch('http://localhost:8000/api/execution/apikey', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ api_key_index: e.target.value }) });
                    }
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      fetch('http://localhost:8000/api/execution/apikey', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ api_key_index: e.target.value }) });
                      e.target.blur();
                    }
                  }}
                  className="mono"
                  style={{ width: '80px', padding: '4px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border-subtle)', color: 'white', borderRadius: '4px', textAlign: 'right' }}
                />
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-dim)' }}>Last Tx Nonce</span>
              <span className="mono" style={{ color: 'var(--text-muted)' }}>{execution.last_nonce}</span>
            </div>
          </div>
        </div>

        {/* Balance Card */}
        <div className="glass-panel" style={{ padding: '20px', background: 'linear-gradient(135deg, rgba(6, 182, 212, 0.1) 0%, rgba(10, 13, 20, 0.75) 100%)', borderColor: 'var(--accent-cyan-glow)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', color: 'var(--accent-cyan)', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 700 }}>
            <Wallet size={14} /> Balance & Positions
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
              <span style={{ color: 'var(--text-dim)' }}>Equity</span>
              <span className="mono" style={{ fontSize: '24px', fontWeight: 700, lineHeight: 1 }}>
                ${(execution.equity_usd || 0).toLocaleString('en-US', {minimumFractionDigits: 2})}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-dim)' }}>Unrealized PnL</span>
              <span className="mono" style={{ fontWeight: 700, color: (execution.unrealized_pnl || 0) >= 0 ? 'var(--accent-bull)' : 'var(--accent-bear)' }}>
                ${(execution.unrealized_pnl || 0).toLocaleString('en-US', {minimumFractionDigits: 2})}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-dim)' }}>BTC Position</span>
              <span className="mono" style={{ fontWeight: 700 }}>
                {execution.position} BTC
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Transaction History */}
      <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', minHeight: '300px' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <History size={16} color="var(--accent-purple)" />
          <h3 style={{ fontSize: '14px', fontWeight: 600, margin: 0 }}>Recent Executed Trades</h3>
        </div>
        <div style={{ padding: '0', overflowX: 'auto' }}>
          <table className="ladder-table" style={{ width: '100%', textAlign: 'left' }}>
            <thead>
              <tr style={{ textTransform: 'uppercase', fontSize: '10px', color: 'var(--text-dim)' }}>
                <th style={{ textAlign: 'left', paddingLeft: '20px' }}>Market</th>
                <th style={{ textAlign: 'left' }}>Side</th>
                <th style={{ textAlign: 'left' }}>Date</th>
                <th style={{ textAlign: 'right' }}>Trade Value</th>
                <th style={{ textAlign: 'right' }}>Size</th>
                <th style={{ textAlign: 'right' }}>Price</th>
                <th style={{ textAlign: 'right' }}>Closed PnL</th>
                <th style={{ textAlign: 'right' }}>Fee</th>
                <th style={{ textAlign: 'center' }}>Role</th>
                <th style={{ textAlign: 'center' }}>Type</th>
                <th style={{ textAlign: 'right', paddingRight: '20px' }}>Explorer</th>
              </tr>
            </thead>
            <tbody>
              {history.length === 0 ? (
                <tr>
                  <td colSpan="11" style={{ textAlign: 'center', padding: '30px', color: 'var(--text-dim)' }}>
                    No recent trades found in database.
                  </td>
                </tr>
              ) : (
                history.map((tx, idx) => {
                  const dateObj = new Date(tx.timestamp);
                  const formattedDate = `${dateObj.getMonth()+1}/${dateObj.getDate()}/${dateObj.getFullYear()} ${dateObj.getHours().toString().padStart(2, '0')}:${dateObj.getMinutes().toString().padStart(2, '0')}:${dateObj.getSeconds().toString().padStart(2, '0')}`;
                  
                  let sideLabel = tx.side === 'BUY' ? 'Buy' : 'Sell';
                  let sideColor = tx.side === 'BUY' ? 'var(--accent-bull)' : 'var(--accent-bear)';
                  
                  const tradeValue = tx.exec_price * tx.exec_amount;
                  const fee = tx.fee_paid !== undefined ? `$${tx.fee_paid.toFixed(4)}` : '-';
                  const role = tx.role || 'Taker';
                  const type = tx.type || 'Trade';
                  const pnl = tx.realized_pnl || 0;
                  const pnlColor = pnl > 0 ? 'var(--accent-bull)' : (pnl < 0 ? 'var(--accent-bear)' : 'var(--text-dim)');
                  
                  const explorerUrl = execution.mode === 'MAINNET' 
                    ? `https://explorer.mainnet.zklighter.elliot.ai/tx/${tx.hash}` 
                    : `https://explorer.testnet.zklighter.elliot.ai/tx/${tx.hash}`;

                  return (
                    <tr key={idx} style={{ borderBottom: '1px solid rgba(255,255,255,0.02)', fontSize: '12px' }}>
                      <td style={{ textAlign: 'left', paddingLeft: '20px', fontWeight: 600 }}>{tx.symbol}</td>
                      <td style={{ textAlign: 'left', color: sideColor, fontWeight: 700 }}>{sideLabel}</td>
                      <td style={{ textAlign: 'left', color: 'var(--text-muted)' }}>{formattedDate}</td>
                      <td className="mono" style={{ textAlign: 'right' }}>${tradeValue.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})}</td>
                      <td className="mono" style={{ textAlign: 'right' }}>{tx.exec_amount.toFixed(4)}</td>
                      <td className="mono" style={{ textAlign: 'right' }}>${tx.exec_price.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})}</td>
                      <td className="mono" style={{ textAlign: 'right', color: pnlColor, fontWeight: pnl !== 0 ? 600 : 400 }}>
                        {pnl !== 0 ? (pnl > 0 ? `+$${pnl.toFixed(2)}` : `-$${Math.abs(pnl).toFixed(2)}`) : '-'}
                      </td>
                      <td className="mono" style={{ textAlign: 'right', color: 'var(--text-dim)' }}>{fee}</td>
                      <td style={{ textAlign: 'center', color: role === 'Maker' ? 'var(--accent-cyan)' : 'var(--text-dim)', fontSize: '11px', textTransform: 'uppercase' }}>{role}</td>
                      <td style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '11px' }}>{type}</td>
                      <td style={{ textAlign: 'right', paddingRight: '20px' }}>
                        {tx.hash ? (
                          <a href={explorerUrl} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent-purple)', textDecoration: 'none', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '4px', fontSize: '11px' }}>
                            Explorer <ExternalLink size={10} />
                          </a>
                        ) : (
                          <span style={{ color: 'var(--text-dim)', fontSize: '11px' }}>-</span>
                        )}
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
