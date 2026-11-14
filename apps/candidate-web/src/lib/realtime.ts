import { API_BASE } from '../api/client'
import { getAccessToken } from './tokenStorage'

export type LiveState = 'idle' | 'requesting-mic' | 'negotiating' | 'connected' | 'closed' | 'error'

export interface LiveSession {
  close: () => void
}

/**
 * Browser side of the server-mediated realtime call.
 *
 * The provider key never reaches the browser: we post the SDP offer to
 * `/voice-sessions/{id}/connect`, which creates the upstream call and returns
 * the answer SDP. Audio then flows over WebRTC.
 */
export async function connectInterview(
  sessionId: string,
  audioElement: HTMLAudioElement,
  onState: (state: LiveState, detail?: string) => void,
): Promise<LiveSession> {
  let stream: MediaStream | null = null
  let peer: RTCPeerConnection | null = null

  const close = () => {
    stream?.getTracks().forEach((track) => track.stop())
    stream = null
    if (peer) {
      peer.ontrack = null
      peer.close()
      peer = null
    }
    audioElement.srcObject = null
    onState('closed')
  }

  try {
    onState('requesting-mic')
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('当前浏览器不支持麦克风采集。请使用最新版 Chrome / Edge，并通过 localhost 或 HTTPS 访问。')
    }
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })

    onState('negotiating')
    peer = new RTCPeerConnection()
    peer.ontrack = (event) => {
      audioElement.srcObject = event.streams[0] ?? new MediaStream([event.track])
      void audioElement.play().catch(() => undefined)
    }
    stream.getTracks().forEach((track) => peer?.addTrack(track, stream as MediaStream))

    const offer = await peer.createOffer()
    await peer.setLocalDescription(offer)

    // Non-trickle: wait for the full candidate set before posting the offer.
    await new Promise<void>((resolve) => {
      if (!peer || peer.iceGatheringState === 'complete') return resolve()
      const timeout = window.setTimeout(() => resolve(), 2500)
      peer.addEventListener('icegatheringstatechange', () => {
        if (peer?.iceGatheringState === 'complete') {
          window.clearTimeout(timeout)
          resolve()
        }
      })
    })

    const token = getAccessToken()
    const response = await fetch(`${API_BASE}/voice-sessions/${sessionId}/connect`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token ?? ''}`,
        'Content-Type': 'application/sdp',
      },
      body: peer.localDescription?.sdp ?? '',
    })

    if (!response.ok) {
      let message = `接通失败（HTTP ${response.status}）`
      try {
        const body = (await response.json()) as { message?: string; code?: string }
        if (body.message) message = body.code ? `${body.message}（${body.code}）` : body.message
      } catch {
        // Non-JSON body: keep the status-based message.
      }
      throw new Error(message)
    }

    const answerSdp = await response.text()
    await peer.setRemoteDescription({ type: 'answer', sdp: answerSdp })
    onState('connected')

    return { close }
  } catch (error) {
    close()
    onState('error', error instanceof Error ? error.message : '语音面试连接失败。')
    throw error
  }
}
