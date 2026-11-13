/**
 * Screening WebSocket connection factory.
 *
 * Connection lifecycle, retries and cleanup stay in the consuming component
 * (ProcessingPanel) so the socket has a single owner.
 */
export function createWebSocket(sessionId: string): WebSocket {
  const configured = import.meta.env.VITE_WS_URL
  const wsBase =
    (configured && configured.replace(/\/$/, '')) ||
    (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host

  return new WebSocket(`${wsBase}/ws/${sessionId}`)
}
