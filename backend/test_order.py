import asyncio
import os
import sys
import time
from dotenv import load_dotenv

# Ensure backend root is on PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from app.execution.lighter_client import LighterExecutionClient

async def test_manual_order():
    client = LighterExecutionClient(mode="testnet")
    # Force live testnet execution
    client.is_simulation = False
    
    print("\n=======================================================")
    print("  LIGHTER TESTNET LIVE MANUAL ORDER VERIFICATION")
    print("=======================================================")
    print(f"Network: {client.mode.upper()} (Chain ID: {client.chain_id})")
    print(f"Base URL: {client.base_url}")
    print(f"Account Index: {client.account_index}")
    print(f"API Key Index: {client.api_key_index}")
    print(f"Simulation / Paper: {client.is_simulation}")

    # Handle explicit cancellation request
    if "--cancel-id" in sys.argv:
        idx = sys.argv.index("--cancel-id")
        if idx + 1 < len(sys.argv):
            target_order_id = int(sys.argv[idx + 1])
            print(f"\n[Action] Canceling order #{target_order_id}...")
            client.orders[target_order_id] = type("Obj", (), {"symbol": "BTC", "status": "OPEN"})()
            res = await client.cancel_order(target_order_id)
            print(f"Cancel result: {'SUCCESS' if res else 'FAILED'}")
            await client.aclose()
            return

    # 1. Fetch dynamic market spec
    spec = await client.get_market_spec("BTC")
    print(f"\n[1] Resolved dynamic market spec for BTC:")
    print(f"    Market ID: {spec['market_id']}")
    print(f"    Price Decimals: {spec['price_decimals']} (Scale: {spec['price_scale']})")
    print(f"    Size Decimals:  {spec['size_decimals']} (Scale: {spec['size_scale']})")
    print(f"    Min Base: {spec['min_base_amount']} BTC | Min Quote: ${spec['min_quote_amount']}")

    # 2. Check initial nonce
    initial_nonce = await client.fetch_next_nonce()
    print(f"\n[2] Initial nextNonce from exchange: {initial_nonce}")

    # 3. Place a BUY Limit Order safely below market
    # e.g. Price: $70,000.0, Size: 0.0002 BTC -> Notional: $14.0 (> $10 min quote)
    test_price = 70000.0
    test_amount = 0.00020

    print(f"\n[3] Sending manual limit order:")
    print(f"    Symbol: BTC, Side: BUY, Type: LIMIT (Post-Only)")
    print(f"    Price: ${test_price:,.1f}, Amount: {test_amount} BTC (Notional: ${test_price * test_amount:.2f})")

    try:
        order = await client.place_order(
            symbol="BTC",
            side="BUY",
            price=test_price,
            amount=test_amount,
            post_only=True,
            reduce_only=False,
        )

        print("\n--- Place Order Result ---")
        print(f"Status: {order.status}")
        print(f"Client Order Index: {order.client_order_index}")
        print(f"Tx Hash: {order.exchange_order_id}")

        if order.status == "OPEN" and order.exchange_order_id:
            print("\n[SUCCESS] Order accepted and confirmed by Lighter Testnet Sequencer!")
            
            # 4. Check active orders on exchange with auth token
            signer = await client.get_signer_client()
            if signer:
                token, _ = signer.create_auth_token_with_expiry(signer.DEFAULT_10_MIN_AUTH_EXPIRY, api_key_index=client.api_key_index)
                http = await client.get_http_client()
                active_res = await http.get(
                    f"{client.base_url}/api/v1/accountActiveOrders?account_index={client.account_index}&market_id={spec['market_id']}",
                    headers={"Authorization": token}
                )
                if active_res.status_code == 200:
                    orders = active_res.json().get("orders", [])
                    print(f"\n[4] Active Orders in Lighter Testnet Orderbook: {len(orders)}")
                    for o in orders:
                        print(f"    - OrderIndex: {o.get('order_index')} | Price: ${o.get('price')} | BaseAmount: {o.get('remaining_base_amount')} | Status: {o.get('status')}")

            should_cancel = "--cancel" in sys.argv
            if should_cancel:
                print("\nWaiting 2 seconds before canceling test order (--cancel specified)...")
                await asyncio.sleep(2)
                print(f"\n[5] Canceling test order #{order.client_order_index}...")
                canceled = await client.cancel_order(order.client_order_index)
                print(f"Cancel status: {'SUCCESS (Order Canceled)' if canceled else 'FAILED'}")
            else:
                print(f"\n>>> Order is LEFT OPEN for manual verification on Lighter Testnet! <<<")
                print(f"    Account Index: {client.account_index}")
                print(f"    Market: BTC (Market ID: {spec['market_id']})")
                print(f"    Side: BUY | Price: ${test_price:,.1f} | Amount: {test_amount} BTC")
                print(f"    Tx Hash: {order.exchange_order_id}")
                print(f"    To cancel this order later, run: ./backend/venv/bin/python backend/test_order.py --cancel-id {order.client_order_index}")

            # 6. Verify clean state
            after_nonce = await client.fetch_next_nonce()
            print(f"\n[5] Current nextNonce: {after_nonce}")
            print("\nOrder verification completed successfully!")
        else:
            print("\n[FAILED] Order was not accepted.")

    finally:
        await client.aclose()

if __name__ == "__main__":
    asyncio.run(test_manual_order())
