"""
Finnhub WebSocket for real-time trade data.
Runs in a background daemon thread during live mode.
"""
import json
import time
import logging
import threading
import websocket

logger = logging.getLogger(__name__)


class FinnhubWebSocket:
    """Real-time trade stream via Finnhub WebSocket."""

    def __init__(self, api_key: str, symbols: list[str] = None):
        self.api_key = api_key
        self.url = f"wss://ws.finnhub.io?token={api_key}"
        self.symbols = set(symbols or [])
        self._prices: dict[str, dict] = {}  # {symbol: {price, volume, timestamp}}
        self._lock = threading.Lock()
        self._ws = None
        self._running = False

    def get_price(self, symbol: str) -> dict | None:
        """Get latest price data for a symbol (thread-safe)."""
        with self._lock:
            return self._prices.get(symbol)

    def get_all_prices(self) -> dict:
        """Get all latest prices (thread-safe)."""
        with self._lock:
            return dict(self._prices)

    def subscribe(self, symbol: str):
        """Subscribe to a new symbol."""
        self.symbols.add(symbol)
        if self._ws:
            try:
                self._ws.send(json.dumps({"type": "subscribe", "symbol": symbol}))
            except Exception:
                pass

    def unsubscribe(self, symbol: str):
        """Unsubscribe from a symbol."""
        self.symbols.discard(symbol)
        if self._ws:
            try:
                self._ws.send(json.dumps({"type": "unsubscribe", "symbol": symbol}))
            except Exception:
                pass

    def run(self):
        """Run the WebSocket connection (blocking — call from a thread)."""
        self._running = True
        retry_delay = 1

        while self._running:
            try:
                self._ws = websocket.WebSocketApp(
                    self.url,
                    on_message=self._on_message,
                    on_open=self._on_open,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self._ws.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as e:
                logger.warning(f"WebSocket error: {e}")

            if self._running:
                logger.info(f"Reconnecting in {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)

    def stop(self):
        """Stop the WebSocket connection."""
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

    def _on_open(self, ws):
        """Subscribe to all symbols on connection."""
        logger.info(f"Finnhub WS connected, subscribing to {len(self.symbols)} symbols")
        for symbol in self.symbols:
            ws.send(json.dumps({"type": "subscribe", "symbol": symbol}))

    def _on_message(self, ws, message):
        """Process incoming trade messages."""
        try:
            data = json.loads(message)
            if data.get("type") == "trade":
                for trade in data.get("data", []):
                    symbol = trade.get("s")
                    if symbol:
                        with self._lock:
                            self._prices[symbol] = {
                                "price": trade.get("p", 0),
                                "volume": trade.get("v", 0),
                                "timestamp": trade.get("t", 0),
                            }
        except Exception:
            pass

    def _on_error(self, ws, error):
        logger.warning(f"Finnhub WS error: {error}")

    def _on_close(self, ws, close_code, close_msg):
        logger.info(f"Finnhub WS closed: {close_code} {close_msg}")
