/**
 * Chat Store 测试 — 消息增删、流式状态转换、引用管理
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useChatStore } from '../../src/stores/chat'

describe('ChatStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  describe('addMessage', () => {
    it('adds a user message', () => {
      const store = useChatStore()
      const id = store.addMessage({ role: 'user', content: '你好' })
      expect(id).toBeTruthy()
      expect(store.messages).toHaveLength(1)
      expect(store.messages[0].role).toBe('user')
      expect(store.messages[0].content).toBe('你好')
    })

    it('generates unique IDs for each message', () => {
      const store = useChatStore()
      const id1 = store.addMessage({ role: 'user', content: 'msg1' })
      const id2 = store.addMessage({ role: 'user', content: 'msg2' })
      expect(id1).not.toBe(id2)
    })

    it('sets timestamp on new messages', () => {
      const store = useChatStore()
      store.addMessage({ role: 'user', content: 'test' })
      expect(store.messages[0].timestamp).toBeGreaterThan(0)
    })
  })

  describe('streaming', () => {
    it('startStreaming creates an empty assistant message', () => {
      const store = useChatStore()
      const id = store.startStreaming()
      expect(store.isProcessing).toBe(true)
      expect(store.error).toBe('')
      expect(store.messages).toHaveLength(1)
      expect(store.messages[0].role).toBe('assistant')
      expect(store.messages[0].content).toBe('')
      expect(store.messages[0].isStreaming).toBe(true)
    })

    it('appendToken adds text to streaming message', () => {
      const store = useChatStore()
      const id = store.startStreaming()
      store.appendToken(id, '你好')
      store.appendToken(id, '世界')
      expect(store.messages[0].content).toBe('你好世界')
    })

    it('appendToken ignores unknown message ID', () => {
      const store = useChatStore()
      store.appendToken('nonexistent', 'hello')
      expect(store.messages).toHaveLength(0)
    })

    it('finishStreaming marks message as complete', () => {
      const store = useChatStore()
      const id = store.startStreaming()
      store.appendToken(id, 'hello')
      store.finishStreaming(id, 'qa', [
        { doc_id: '1', source: 'guide.md', matched_sentence: 'test' },
      ])
      expect(store.isProcessing).toBe(false)
      expect(store.currentIntent).toBe('qa')
      expect(store.messages[0].isStreaming).toBe(false)
      expect(store.messages[0].citations).toHaveLength(1)
    })

    it('finishStreaming without citations works', () => {
      const store = useChatStore()
      const id = store.startStreaming()
      store.finishStreaming(id)
      expect(store.isProcessing).toBe(false)
      expect(store.messages[0].citations).toBeUndefined()
    })

    it('finishStreaming with nonexistent ID does not throw', () => {
      const store = useChatStore()
      expect(() => store.finishStreaming('nonexistent')).not.toThrow()
    })
  })

  describe('state management', () => {
    it('setStage updates current stage', () => {
      const store = useChatStore()
      store.setStage('检索中')
      expect(store.currentStage).toBe('检索中')
    })

    it('setError sets error and stops processing', () => {
      const store = useChatStore()
      store.startStreaming()
      store.setError('Something went wrong')
      expect(store.error).toBe('Something went wrong')
      expect(store.isProcessing).toBe(false)
    })

    it('clearMessages resets all state', () => {
      const store = useChatStore()
      store.addMessage({ role: 'user', content: 'test' })
      store.addMessage({ role: 'assistant', content: 'reply' })
      store.currentIntent = 'qa'
      store.error = 'some error'

      store.clearMessages()

      expect(store.messages).toHaveLength(0)
      expect(store.currentIntent).toBe('')
      expect(store.error).toBe('')
    })
  })

  describe('computed', () => {
    it('lastAssistantMsg returns last assistant message', () => {
      const store = useChatStore()
      store.addMessage({ role: 'user', content: 'hello' })
      store.addMessage({ role: 'assistant', content: 'hi there' })

      const last = store.lastAssistantMsg
      expect(last).toBeTruthy()
      expect(last!.role).toBe('assistant')
      expect(last!.content).toBe('hi there')
    })

    it('lastAssistantMsg returns null when no assistant msg', () => {
      const store = useChatStore()
      store.addMessage({ role: 'user', content: 'only user' })
      expect(store.lastAssistantMsg).toBeNull()
    })
  })

  describe('session', () => {
    it('sessionId is empty by default', () => {
      const store = useChatStore()
      expect(store.sessionId).toBe('')
    })

    it('sessionId can be set directly', () => {
      const store = useChatStore()
      store.sessionId = 'test-session-123'
      expect(store.sessionId).toBe('test-session-123')
    })
  })
})
