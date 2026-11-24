
import { useEffect, useRef, useState } from 'react'
import {
  Bot, Plus, Send, Sparkles, User, Zap, Database,
  ShieldCheck, Github, RotateCcw
} from 'lucide-react'

const API_BASE = (
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
).replace(/\/$/, '')

const makeSessionId = () =>
  `s-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`}`

function Meta({ metadata }) {
  return (
    <div className="meta-grid">
      <span
        className={`source-pill ${metadata.resolution_source === 'LLM_CACHE' ? 'cached' : 'live'}`}
        data-testid="meta-source"
      >
        {metadata.resolution_source}
      </span>
      <span data-testid="meta-model"><b>Model</b> {metadata.model}</span>
      <span data-testid="meta-latency"><b>Latency</b> {metadata.latency_ms} ms</span>
      <span data-testid="meta-input-tokens"><b>Input</b> {metadata.input_tokens} tokens</span>
      <span data-testid="meta-output-tokens"><b>Output</b> {metadata.output_tokens} tokens</span>
    </div>
  )
}

export default function App() {
  const [sessionId, setSessionId] = useState(makeSessionId)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [showSettings, setShowSettings] = useState(false)
  const [busy, setBusy] = useState(false)
  const [apiStatus, setApiStatus] = useState('checking')

  const bottomRef = useRef(null)
  const inputRef = useRef(null)
  const busyRef = useRef(false)

  useEffect(() => {
    let active = true

    fetch(`${API_BASE}/health`)
      .then(response => {
        if (!response.ok) throw new Error('API unavailable')
        return response.json()
      })
      .then(() => {
        if (active) setApiStatus('online')
      })
      .catch(() => {
        if (active) setApiStatus('offline')
      })

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    const element = bottomRef.current
    if (element && typeof element.scrollIntoView === 'function') {
      element.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, busy])

  const newChat = () => {
    setSessionId(makeSessionId())
    setMessages([])
    setInput('')
    inputRef.current?.focus()
  }

  const sendMessage = async () => {
    const messageText = input.trim()

    if (!messageText || busyRef.current) return

    busyRef.current = true
    setInput('')
    setMessages(previous => [
      ...previous,
      { role: 'user', content: messageText }
    ])
    setBusy(true)

    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          message: messageText,
          ...(systemPrompt.trim()
            ? { system_prompt: systemPrompt.trim() }
            : {})
        })
      })

      let data = {}
      try {
        data = await response.json()
      } catch {
        data = {}
      }

      if (!response.ok) {
        throw new Error(
          data.detail || `Request failed (${response.status})`
        )
      }

      if (!data.reply) {
        throw new Error('The assistant returned an empty response.')
      }

      setMessages(previous => [
        ...previous,
        {
          role: 'assistant',
          content: data.reply,
          metadata: data.metadata
        }
      ])

      setApiStatus('online')
    } catch (error) {
      setMessages(previous => [
        ...previous,
        {
          role: 'error',
          content: error.message || 'Unable to reach the assistant. Please try again.'
        }
      ])

      if (error instanceof TypeError) {
        setApiStatus('offline')
      }
    } finally {
      busyRef.current = false
      setBusy(false)
      inputRef.current?.focus()
    }
  }

  const handleSubmit = event => {
    event.preventDefault()
    sendMessage()
  }

  const handleKeyDown = event => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Sparkles size={19} /></div>
          <div>
            <strong>LYFTR<span>.AI</span></strong>
            <small>INTELLIGENCE, IN MOTION</small>
          </div>
        </div>

        <button className="new-chat" onClick={newChat}>
          <Plus size={17} /> New conversation
        </button>

        <div className="side-label">WORKSPACE</div>
        <div className="side-link active">
          <Bot size={17} /> AI Assistant
        </div>

        <div className="side-card">
          <div className="side-card-icon"><ShieldCheck size={17} /></div>
          <div>
            <b>Resilient by design</b>
            <p>Automatic key failover keeps conversations moving.</p>
          </div>
        </div>

        <div className="sidebar-bottom">
          <div className="status-line">
            <span className={`status-dot ${apiStatus}`} />
            API {apiStatus === 'online'
              ? 'connected'
              : apiStatus === 'offline'
                ? 'unavailable'
                : 'checking'}
          </div>
          <a href="https://github.com" target="_blank" rel="noreferrer">
            <Github size={15} /> Built for LYFTR AI
          </a>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div>
            <span className="eyebrow">YOUR AI WORKSPACE</span>
            <h1>AI Assistant</h1>
          </div>
          <div className="top-actions">
            <span className="secure-tag">
              <ShieldCheck size={14} /> Secure session
            </span>
            <button
              className="icon-button"
              title="New chat"
              onClick={newChat}
            >
              <RotateCcw size={17} />
            </button>
          </div>
        </header>

        <section className="chat-area">
          {messages.length === 0 ? (
            <div className="welcome">
              <div className="welcome-orb"><Sparkles size={25} /></div>
              <div className="eyebrow">WELCOME TO LYFTR AI</div>
              <h2>
                Ideas move faster
                <br />
                <em>when you think together.</em>
              </h2>
              <p>
                Ask a question, explore an idea, or pick up where you left off.
                Your conversation stays in context.
              </p>

              <div className="suggestions">
                <button
                  onClick={() => setInput('Explain how API key failover works in a chatbot.')}
                >
                  <Zap size={16} />
                  <span>
                    <b>Explore resilience</b>
                    <small>How does key failover work?</small>
                  </span>
                </button>

                <button
                  onClick={() => setInput('Explain response caching and why it improves performance.')}
                >
                  <Database size={16} />
                  <span>
                    <b>Understand caching</b>
                    <small>Make responses faster</small>
                  </span>
                </button>
              </div>
            </div>
          ) : (
            <div className="messages-list">
              {messages.map((message, index) => (
                <div
                  className={`message-row ${message.role}`}
                  key={`${index}-${message.role}`}
                >
                  <div className={`avatar ${message.role}`}>
                    {message.role === 'user'
                      ? <User size={17} />
                      : message.role === 'assistant'
                        ? <Bot size={18} />
                        : <span>!</span>}
                  </div>

                  <div className="message-content">
                    {message.role === 'assistant' ? (
                      <div data-testid="assistant-message">
                        <div className="message-text">{message.content}</div>
                        {message.metadata && (
                          <Meta metadata={message.metadata} />
                        )}
                      </div>
                    ) : (
                      <div className={`message-text ${message.role === 'error' ? 'error-text' : ''}`}>
                        {message.content}
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {busy && (
                <div className="message-row assistant">
                  <div className="avatar assistant"><Bot size={18} /></div>
                  <div className="typing">
                    <i /><i /><i /> <span>Thinking</span>
                  </div>
                </div>
              )}

              <div ref={bottomRef} />
            </div>
          )}
        </section>

        <footer className="composer-wrap">
          {showSettings && (
            <div className="settings-panel">
              <label htmlFor="system-prompt">
                SYSTEM PROMPT
                <span>Optional · applies to this session</span>
              </label>
              <textarea
                id="system-prompt"
                data-testid="system-prompt-input"
                value={systemPrompt}
                onChange={event => setSystemPrompt(event.target.value)}
                placeholder="e.g. You are a concise technical mentor..."
                rows={2}
              />
            </div>
          )}

          <form className="composer" onSubmit={handleSubmit}>
            <textarea
              ref={inputRef}
              data-testid="chat-input"
              value={input}
              onChange={event => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message LYFTR AI..."
              rows={1}
              disabled={busy}
            />

            <button
              className="send-button"
              data-testid="send-button"
              type="submit"
              disabled={!input.trim() || busy}
              aria-label="Send message"
            >
              <Send size={17} />
            </button>
          </form>

          <div className="composer-footer">
            <button
              onClick={() => setShowSettings(value => !value)}
              className="settings-toggle"
            >
              {showSettings ? 'Hide' : 'Set'} system prompt
            </button>
            <span>Enter to send · Shift + Enter for new line</span>
          </div>
        </footer>
      </main>
    </div>
  )
}
