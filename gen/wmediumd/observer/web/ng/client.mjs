export class ObserverClient extends EventTarget {
  constructor() {
    super(); this.interest = { topics: [] }; this.data = {}; this.sequence = '0'; this.backoff = 500; this.closed = false;
    this.connect();
    this.heartbeat = setInterval(() => this.send(), 5000);
    document.addEventListener('visibilitychange', () => this.send());
  }
  connect() {
    if (this.closed) return;
    this.socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/v2/stream`);
    this.socket.onopen = () => { this.backoff = 500; this.send('resync'); this.status('Connected'); };
    this.socket.onmessage = event => {
      try {
        const message = JSON.parse(event.data);
        if (!['snapshot', 'delta'].includes(message.type)) return;
        if (message.type === 'delta' && message.baseline !== this.sequence) { this.send('resync'); this.status('Resynchronizing'); return; }
        this.sequence = message.sequence;
        this.data = message.type === 'snapshot' ? message.data : { ...this.data, ...message.data };
        this.dispatchEvent(new CustomEvent('data', { detail: { data: this.data, patch: message.type === 'snapshot' ? this.data : message.data } }));
      } catch { this.status('Invalid update; resynchronizing'); this.send('resync'); }
    };
    this.socket.onclose = () => {
      if (this.closed) return;
      this.status('Disconnected · retrying');
      this.retry = setTimeout(() => this.connect(), this.backoff);
      this.backoff = Math.min(10000, this.backoff * 2);
    };
    this.socket.onerror = () => this.socket.close();
  }
  status(message) { this.dispatchEvent(new CustomEvent('status', { detail: message })); }
  subscribe(interest) { this.interest = interest; this.send(); }
  send(type = 'subscribe') {
    if (this.socket?.readyState !== WebSocket.OPEN) return;
    const interest = document.hidden ? { topics: [] } : this.interest;
    this.socket.send(JSON.stringify({ type: interest.topics.length ? type : 'unsubscribe', ...interest }));
  }
  close() { this.closed = true; clearInterval(this.heartbeat); clearTimeout(this.retry); this.socket?.close(); }
}
