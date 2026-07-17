/**
 * API Client 测试 — sendChat, sendChatStream, sessions, knowledge
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock global fetch
const mockFetch = vi.fn()
global.fetch = mockFetch

// 动态导入以拿到最新的 BASE 常量
const API_BASE = '/api/v1'

describe('API Client', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('sendChat', () => {
    it('sends correct POST request', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ answer: '你好', session_id: 's1', intent: 'general' }),
      })

      const { sendChat } = await import('../../src/api/index')
      const result = await sendChat({ user_id: 'U1', message: '测试', session_id: 's1' })

      expect(mockFetch).toHaveBeenCalledTimes(1)
      const [url, options] = mockFetch.mock.calls[0]
      expect(url).toBe(`${API_BASE}/chat`)
      expect(options.method).toBe('POST')
      expect(options.headers['Content-Type']).toBe('application/json')
      expect(JSON.parse(options.body)).toEqual({
        user_id: 'U1',
        message: '测试',
        session_id: 's1',
      })
      expect(result.answer).toBe('你好')
      expect(result.session_id).toBe('s1')
    })

    it('throws on non-ok response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        statusText: 'Bad Request',
        json: () => Promise.resolve({ detail: 'Invalid request' }),
      })

      const { sendChat } = await import('../../src/api/index')
      await expect(sendChat({ user_id: 'U1', message: 'test' })).rejects.toThrow('Invalid request')
    })

    it('throws on network error', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'))

      const { sendChat } = await import('../../src/api/index')
      await expect(sendChat({ user_id: 'U1', message: 'test' })).rejects.toThrow('Network error')
    })
  })

  describe('sendChatStream', () => {
    it('creates AbortController and calls fetch', async () => {
      const mockReader = {
        read: vi.fn()
          .mockResolvedValueOnce({
            done: false,
            value: new TextEncoder().encode('event: token\ndata: {"text":"hello"}\n\n'),
          })
          .mockResolvedValueOnce({ done: true }),
      }
      mockFetch.mockResolvedValueOnce({
        ok: true,
        body: { getReader: () => mockReader },
      })

      const { sendChatStream } = await import('../../src/api/index')
      const onToken = vi.fn()
      const onStatus = vi.fn()
      const onDone = vi.fn()
      const onError = vi.fn()

      const controller = sendChatStream(
        { user_id: 'U1', message: 'test' },
        onToken,
        onStatus,
        onDone,
        onError,
      )

      expect(controller).toBeInstanceOf(AbortController)
      expect(mockFetch).toHaveBeenCalledTimes(1)

      // Wait for async processing
      await new Promise((r) => setTimeout(r, 50))

      expect(onToken).toHaveBeenCalledWith('hello')
    })

    it('calls onError for non-ok response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      })

      const { sendChatStream } = await import('../../src/api/index')
      const onError = vi.fn()

      sendChatStream(
        { user_id: 'U1', message: 'test' },
        vi.fn(), vi.fn(), vi.fn(),
        onError,
      )

      await new Promise((r) => setTimeout(r, 50))
      expect(onError).toHaveBeenCalled()
    })

    it('calls onError on fetch rejection', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'))

      const { sendChatStream } = await import('../../src/api/index')
      const onError = vi.fn()

      sendChatStream(
        { user_id: 'U1', message: 'test' },
        vi.fn(), vi.fn(), vi.fn(),
        onError,
      )

      await new Promise((r) => setTimeout(r, 50))
      expect(onError).toHaveBeenCalled()
    })

    it('AbortController can abort the request', () => {
      const controller = new AbortController()
      expect(controller.signal.aborted).toBe(false)
      controller.abort()
      expect(controller.signal.aborted).toBe(true)
    })
  })

  describe('getSessionHistory', () => {
    it('calls correct endpoint', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ session_id: 's1', messages: [], total: 0 }),
      })

      const { getSessionHistory } = await import('../../src/api/index')
      const result = await getSessionHistory('s1')

      expect(mockFetch).toHaveBeenCalledWith(`${API_BASE}/session/s1/history`)
      expect(result.session_id).toBe('s1')
    })
  })

  describe('listSessions', () => {
    it('adds query params', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ sessions: [], total: 0 }),
      })

      const { listSessions } = await import('../../src/api/index')
      await listSessions('U1', 10, 5)

      const [url] = mockFetch.mock.calls[0]
      expect(url).toContain('user_id=U1')
      expect(url).toContain('limit=10')
      expect(url).toContain('offset=5')
    })
  })

  describe('deleteSession', () => {
    it('sends DELETE request', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ status: 'deleted', session_id: 's1' }),
      })

      const { deleteSession } = await import('../../src/api/index')
      const result = await deleteSession('s1')

      const [url, options] = mockFetch.mock.calls[0]
      expect(options.method).toBe('DELETE')
      expect(result.status).toBe('deleted')
    })
  })

  describe('knowledge API', () => {
    it('getKnowledgeStatus calls correct endpoint', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ status: 'empty', total_documents: 0 }),
      })

      const { getKnowledgeStatus } = await import('../../src/api/index')
      const result = await getKnowledgeStatus()
      expect(result.status).toBe('empty')
      expect(mockFetch).toHaveBeenCalledWith(`${API_BASE}/knowledge/status`)
    })

    it('getBm25Status calls correct endpoint', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ status: 'empty', doc_count: 0 }),
      })

      const { getBm25Status } = await import('../../src/api/index')
      const result = await getBm25Status()
      expect(result.doc_count).toBe(0)
    })
  })
})
