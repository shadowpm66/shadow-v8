# Shadow v8 AWS Deployment

This keeps the same EC2 style as the current Shadow bot: one Python app, `.env`
credentials, logs on disk, and optional broker services.

## 1. Upload Code

From your local machine:

```bash
scp -r shadow_v8 requirements.txt .env.example ubuntu@YOUR_EC2_IP:~/shadow-v8/
```

If the folder does not exist yet:

```bash
ssh ubuntu@YOUR_EC2_IP
mkdir -p ~/shadow-v8
exit
```

Then re-run the `scp` command.

## 2. Create Python Environment

On EC2:

```bash
cd ~/shadow-v8
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 3. Create `.env`

```bash
cp .env.example .env
nano .env
```

Start safely:

```text
CRYPTO_LIVE_TRADING_ENABLED=false
STOCK_LIVE_TRADING_ENABLED=false
IBKR_ENABLED=false
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=8501
DASHBOARD_TOKEN=<DASHBOARD_TOKEN>
SCAN_INTERVAL_SEC=300
SHADOW_EXECUTION_MODE=scan_only
PAPER_ACCOUNT_BALANCE=10000
TELEGRAM_ALERTS_ENABLED=false
```

Only enable IBKR after IB Gateway / paper trading is stable.

## 4. Smoke Test

```bash
source venv/bin/activate
SHADOW_RUN_ONCE=true python -m shadow_v8.main
```

Expected output includes:

```text
Shadow v8 foundation loaded.
Enabled assets: ['ETHUSDT']
Stock scanner enabled: True
```

## 5. Run With systemd

Create service:

```bash
sudo nano /etc/systemd/system/shadow-v8-engine.service
```

Paste:

```ini
[Unit]
Description=Shadow v8 Engine
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/home/ubuntu/shadow-v8
ExecStart=/home/ubuntu/shadow-v8/venv/bin/python -m shadow_v8.main
Restart=always
RestartSec=60
User=ubuntu
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable shadow-v8-engine
sudo systemctl start shadow-v8-engine
sudo systemctl status shadow-v8-engine
```

View logs:

```bash
journalctl -u shadow-v8-engine -f
```

To test paper positions without live orders:

```bash
cd ~/shadow-v8
printf "\nSHADOW_EXECUTION_MODE=paper\nPAPER_ACCOUNT_BALANCE=10000\n" >> .env
sudo systemctl restart shadow-v8-engine
sudo journalctl -u shadow-v8-engine -n 40 --no-pager
```

Return to scanner-only mode:

```bash
cd ~/shadow-v8
sed -i '/^SHADOW_EXECUTION_MODE=/d' .env
printf "\nSHADOW_EXECUTION_MODE=scan_only\n" >> .env
sudo systemctl restart shadow-v8-engine
```

Enable Telegram alerts after adding `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`:

```bash
cd ~/shadow-v8
sed -i '/^TELEGRAM_ALERTS_ENABLED=/d' .env
printf "\nTELEGRAM_ALERTS_ENABLED=true\nTELEGRAM_TOP_SETUP_MIN_SCORE=45\n" >> .env
sudo systemctl restart shadow-v8-engine
sudo journalctl -u shadow-v8-engine -n 40 --no-pager
```

## 6. Dashboard Test

The first dashboard binds to localhost by default. This is intentional so it is
not exposed to the public internet while testing.

After running the scanner once:

```bash
python -m shadow_v8.main
python -m shadow_v8.dashboard.app
```

In another EC2 terminal:

```bash
curl http://127.0.0.1:8501
```

If you set `DASHBOARD_TOKEN`, pass it as either a query string or header:

```bash
curl "http://127.0.0.1:8501?token=YOUR_TOKEN"
curl -H "X-Shadow-Token: YOUR_TOKEN" http://127.0.0.1:8501
```

Do not bind the dashboard to `0.0.0.0` until authentication and the EC2 security
group rules are reviewed.

## 7. IBKR Note

Bybit crypto can run like the current bot. Direct stock execution needs IB Gateway
or TWS running on the server or reachable from the server.

Recommended first stock mode:

```text
Stocks: scan + Telegram alerts
IBKR execution: disabled
```

Then later:

```text
IBKR paper trading
IBKR live trading
```

## 8. Bybit Pre-Live Validation Audit

Before any Bybit live unlock, pull the latest GitHub `main` on EC2 and run the
validate-only audit. This does not place orders and does not print secrets:

```bash
cd ~/shadow-v8
git pull --ff-only
set -a && source .env && set +a
python -m shadow_v8.tools.ec2_prelive_sequence_report --symbols ETHUSDT,BTCUSDT --compact
python -m shadow_v8.tools.ec2_prelive_validation_audit --symbols ETHUSDT,BTCUSDT --compact
```

For the read-only private validation step, run:

```bash
python -m shadow_v8.tools.ec2_prelive_sequence_report --symbols ETHUSDT,BTCUSDT --execute-private-validation --compact
python -m shadow_v8.tools.ec2_prelive_validation_audit --symbols ETHUSDT,BTCUSDT --execute-private-validation --compact
```

After private validation succeeds and after `DASHBOARD_TOKEN` has been rotated,
run the final manual live-unlock review. This still does not place orders and
does not set the live-unlock environment variable:

```bash
python -m shadow_v8.tools.ec2_prelive_sequence_report --symbols ETHUSDT,BTCUSDT --execute-private-validation --dashboard-token-rotated --compact
python -m shadow_v8.tools.bybit_live_unlock_review --symbols ETHUSDT,BTCUSDT --execute-private-validation --dashboard-token-rotated --compact
```

Keep `SHADOW_LIVE_UNLOCK_BROKERS` empty until the final live-review step.
Rotate `DASHBOARD_TOKEN` before live trading because an earlier dashboard token
was exposed during setup discussion.
