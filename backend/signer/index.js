const express = require('express');
const { signCreateOrder, signCancelOrder, signCancelAllOrders, signUpdateLeverage } = require('@hitesh23k/lighter-sdk');

const app = express();
app.use(express.json());

app.post('/sign_create_order', async (req, res) => {
    try {
        const { ctx, input } = req.body;
        const signedTx = await signCreateOrder(ctx, input);
        res.json({ success: true, txType: signedTx.txType, txInfo: signedTx.txInfo });
    } catch (e) {
        console.error("/sign_create_order error:", e.message);
        res.status(400).json({ success: false, error: e.message });
    }
});

app.post('/sign_cancel_order', async (req, res) => {
    try {
        const { ctx, input } = req.body;
        const signedTx = await signCancelOrder(ctx, input);
        res.json({ success: true, txType: signedTx.txType, txInfo: signedTx.txInfo });
    } catch (e) {
        console.error("/sign_cancel_order error:", e.message);
        res.status(400).json({ success: false, error: e.message });
    }
});

app.post('/sign_cancel_all_orders', async (req, res) => {
    try {
        const { ctx, input } = req.body;
        const signedTx = await signCancelAllOrders(ctx, input);
        res.json({ success: true, txType: signedTx.txType, txInfo: signedTx.txInfo });
    } catch (e) {
        console.error("/sign_cancel_all_orders error:", e.message);
        res.status(400).json({ success: false, error: e.message });
    }
});

app.post('/sign_update_leverage', async (req, res) => {
    try {
        const { ctx, input } = req.body;
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
