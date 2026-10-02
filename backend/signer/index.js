const express = require('express');
const { signCreateOrder, signCancelOrder, signCancelAllOrders, signUpdateLeverage } = require('@hitesh23k/lighter-sdk');

const app = express();
app.use(express.json());

function sanitizeCtx(ctx) {
    if (!ctx) return ctx;
    return {
        ...ctx,
        url: String(ctx.url || ''),
        apiPrivateKey: String(ctx.apiPrivateKey || ''),
        chainId: Number(ctx.chainId != null ? ctx.chainId : 300),
        apiKeyIndex: Number(ctx.apiKeyIndex != null ? ctx.apiKeyIndex : 4),
        accountIndex: Number(ctx.accountIndex != null ? ctx.accountIndex : 0),
    };
}

function sanitizeInput(input) {
    if (!input) return input;
    const sanitized = { ...input };
    if ('marketIndex' in sanitized) sanitized.marketIndex = Number(sanitized.marketIndex);
    if ('clientOrderIndex' in sanitized) sanitized.clientOrderIndex = Number(sanitized.clientOrderIndex);
    if ('baseAmount' in sanitized) sanitized.baseAmount = Number(sanitized.baseAmount);
    if ('price' in sanitized) sanitized.price = Number(sanitized.price);
    if ('isAsk' in sanitized) sanitized.isAsk = Boolean(sanitized.isAsk);
    if ('orderType' in sanitized) sanitized.orderType = Number(sanitized.orderType || 0);
    if ('timeInForce' in sanitized) sanitized.timeInForce = Number(sanitized.timeInForce || 0);
    if ('reduceOnly' in sanitized) sanitized.reduceOnly = Boolean(sanitized.reduceOnly);
    if ('orderExpiry' in sanitized) sanitized.orderExpiry = Number(sanitized.orderExpiry || 0);
    if ('nonce' in sanitized) sanitized.nonce = Number(sanitized.nonce);
    if ('orderIndex' in sanitized) sanitized.orderIndex = Number(sanitized.orderIndex);
    if ('initialMarginFraction' in sanitized) sanitized.initialMarginFraction = Number(sanitized.initialMarginFraction);
    if ('marginMode' in sanitized) sanitized.marginMode = Number(sanitized.marginMode || 0);
    return sanitized;
}

app.post('/sign_create_order', async (req, res) => {
    try {
        const ctx = sanitizeCtx(req.body.ctx);
        const input = sanitizeInput(req.body.input);
        const signedTx = await signCreateOrder(ctx, input);
        res.json({ success: true, txType: signedTx.txType, txInfo: signedTx.txInfo });
    } catch (e) {
        console.error("/sign_create_order error:", e.message);
        res.status(400).json({ success: false, error: e.message });
    }
});

app.post('/sign_cancel_order', async (req, res) => {
    try {
        const ctx = sanitizeCtx(req.body.ctx);
        const input = sanitizeInput(req.body.input);
        const signedTx = await signCancelOrder(ctx, input);
        res.json({ success: true, txType: signedTx.txType, txInfo: signedTx.txInfo });
    } catch (e) {
        console.error("/sign_cancel_order error:", e.message);
        res.status(400).json({ success: false, error: e.message });
    }
});

app.post('/sign_cancel_all_orders', async (req, res) => {
    try {
        const ctx = sanitizeCtx(req.body.ctx);
        const input = sanitizeInput(req.body.input);
        const signedTx = await signCancelAllOrders(ctx, input);
        res.json({ success: true, txType: signedTx.txType, txInfo: signedTx.txInfo });
    } catch (e) {
        console.error("/sign_cancel_all_orders error:", e.message);
        res.status(400).json({ success: false, error: e.message });
    }
});

app.post('/sign_update_leverage', async (req, res) => {
    try {
        const ctx = sanitizeCtx(req.body.ctx);
        const input = sanitizeInput(req.body.input);
        const signedTx = await signUpdateLeverage(ctx, input);
        res.json({ success: true, txType: signedTx.txType, txInfo: signedTx.txInfo });
    } catch (e) {
        console.error("/sign_update_leverage error:", e.message);
        res.status(400).json({ success: false, error: e.message });
    }
});

const PORT = 3001;
app.listen(PORT, () => {
    console.log(`Lighter Node Signer running on port ${PORT}`);
});
