---
trigger: always_on
---

# Lighter integration rules

## Sources of truth
- Docs and API reference: https://apidocs.lighter.xyz (index: https://apidocs.lighter.xyz/llms.txt; append .md to any page)
- Signer: https://github.com/elliottech/lighter-go (WASM: wasm/main.go)
- Look things up before writing code. Do not guess endpoint names, parameters or enum values.

## Environments
- Mainnet: https://mainnet.zklighter.elliot.ai, wss://mainnet.zklighter.elliot.ai/stream, chainId 304
- Testnet: https://testnet.zklighter.elliot.ai, wss://testnet.zklighter.elliot.ai/stream, chainId 300
- Default to testnet in examples and tests.

## Accounts and keys
- An L1 (Ethereum) address owns one or more integer account indexes (master + sub-accounts).
- API keys are separate from the Ethereum key. Use API key indexes 4–254 (0–3 are reserved).
- Registering an API key (ChangePubKey) requires the L1 wallet signature over `messageToSign`, set as `L1Sig` in tx_info.
- Never hard-code, log or commit private keys. Load them from env/secret storage.
- Never put a shared/server API key in frontend code.
- For read-only use cases, use read-only tokens (`ro:...`), not API keys.

## Numbers
- Prices and sizes are integers: value × 10^decimals, using `price_decimals` / `size_decimals` from GET /api/v1/orderBookDetails for that market.
- Never hard-code market IDs or decimals outside tests.
- Enforce `min_base_amount` and `min_quote_amount`.
- For taker/market orders, `price` is the worst acceptable price (slippage limit).

## Transactions
- Flow: sign locally with the signer → POST /api/v1/sendTx (form-urlencoded: tx_type, tx_info) → confirm via WebSocket or GET /api/v1/tx.
- `code: 200` means accepted, not executed. Always confirm.
- Nonces are per API key and must increase by 1 unless skipNonce=1. Get with GET /api/v1/nextNonce. Serialize sends per key.
- Before re-signing after an unknown outcome, check the tx status and nextNonce; re-signing with a new nonce can place an order twice.
- orderExpiry is unix milliseconds, 5 minutes–30 days ahead; use 0 for IOC orders.
- clientOrderIndex must be unique across all markets and ≤ 2^48−1.
- Batches: max 50 txs (same account + API key), consecutive nonces, tx_types and tx_infos as JSON-encoded strings. Prefer WebSocket jsonapi/sendtxbatch for more than ~15 txs; large REST bodies can be rejected at the CDN edge.

## WASM signer
- All Sign* functions take positional args; the last two are always apiKeyIndex, accountIndex. Pass 0 for unused args, never undefined.
- Check `result.error` on every call.
- Do all HTTP from JavaScript: pass "" as the CreateClient URL and an explicit nonce; never use CheckClient or nonce=-1 from WASM.
- wasm_exec.js must match the Go version that built the .wasm.

## WebSocket
- Send a frame at least every 2 minutes ({"type":"ping"}); reconnect and resubscribe automatically.
- Order book: snapshot then deltas; verify begin_nonce == previous nonce, else resubscribe.
- Private channels need "auth": <token> (token from CreateAuthToken, max 8h).

## Safety
- Ask a human before: mainnet orders, withdrawals, transfers, changing account tier, registering keys.
- Respect rate limits; back off on HTTP 429/405.