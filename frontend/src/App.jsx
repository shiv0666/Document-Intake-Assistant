import { useMemo, useState } from 'react'
import './App.css'

const initialState = {
  full_name: null,
  home_address: null,
  covers_worldwide_assets: null,
  worldwide_assets_status: 'NOT_PROVIDED',
  has_children: null,
  children_names: [],
  children_names_status: 'NOT_PROVIDED',
  executor: { name: null, relationship: null },
  specific_gifts: null,
  specific_gifts_status: 'NOT_PROVIDED',
  additional_wishes: null,
  additional_wishes_status: 'NOT_PROVIDED',
}

const apiBaseUrl = 'http://127.0.0.1:8000'
const emptyPrompt = 'Hello — I can help you create your fictional Personal Wishes Document. What would you like to record first?'

const displayStatusValue = (status, confirmedValue) => {
  if (status === 'CONFIRMED') return confirmedValue || 'None specified'
  if (status === 'UNKNOWN') return 'Unknown'
  if (status === 'EXPLICIT_NONE') return 'None specified'
  return 'Not yet provided'
}

function App() {
  const [messages, setMessages] = useState([
    { role: 'assistant', text: emptyPrompt },
  ])
  const [input, setInput] = useState('')
  const [state, setState] = useState(initialState)
  const [document, setDocument] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID())

  const startNewConversation = () => {
    setSessionId(crypto.randomUUID())
    setMessages([{ role: 'assistant', text: emptyPrompt }])
    setState(initialState)
    setDocument('')
    setInput('')
  }

  const sendMessage = async () => {
    const message = input.trim()
    if (!message || loading) return

    const nextMessages = [...messages, { role: 'user', text: message }]
    setMessages(nextMessages)
    setInput('')
    setLoading(true)

    try {
      const response = await fetch(`${apiBaseUrl}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session_id: sessionId }),
      })

      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data.detail || 'The assistant could not process that message.')
      }

      setState(data.structured_state || data.state || initialState)
      setDocument(data.document || '')

      const assistantText = data.assistant_message || 'I have updated the record.'
      setMessages((current) => [...current, { role: 'assistant', text: assistantText }])

    } catch (error) {
      setMessages((current) => [
        ...current,
        { role: 'assistant', text: error.message === 'Failed to fetch' ? 'The backend is not reachable. Please make sure the API server is running on port 8000.' : error.message || 'The assistant could not reach the backend. Please try again.' },
      ])
    } finally {
      setLoading(false)
    }
  }

  const summary = useMemo(
    () => [
      ['person', 'Full name', state.full_name || 'Not yet provided'],
      ['home', 'Home address', state.home_address || 'Not yet provided'],
      ['globe', 'Covers worldwide assets', displayStatusValue(state.worldwide_assets_status, state.covers_worldwide_assets === null ? null : state.covers_worldwide_assets ? 'Yes' : 'No')],
      ['family', 'Has children', state.has_children === null ? 'Not yet provided' : state.has_children ? 'Yes' : 'No'],
      ['family', 'Children names', displayStatusValue(state.children_names_status, state.children_names?.join(', '))],
      ['shield', 'Executor name', state.executor?.name || 'Not yet provided'],
      ['person', 'Executor relationship', state.executor?.relationship || 'Not yet provided'],
      ['gift', 'Specific gifts', displayStatusValue(state.specific_gifts_status, state.specific_gifts)],
      ['note', 'Additional wishes', displayStatusValue(state.additional_wishes_status, state.additional_wishes)],
    ],
    [state],
  )

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark">▤</div>
          <div>
            <h1>Document Intake Assistant</h1>
            <p>Create your Personal Wishes Document through a natural conversation</p>
          </div>
        </div>
        <button className="new-conversation" type="button" onClick={startNewConversation}>⊕ <span>New Conversation</span></button>
      </header>

      <main className="layout">
        <section className="panel chat-panel">
          <div className="panel-header panel-title">
            <div className="title-icon">◌</div>
            <div><h2>Conversation</h2><p>Chat naturally to provide your information</p></div>
            <button className="clear-button" type="button" onClick={startNewConversation}>▣ <span>Clear Chat</span></button>
          </div>

          <div className="messages">
            {messages.map((message, index) => (
              <div key={`${message.role}-${index}`} className={`message ${message.role}`}>
                <span className="message-icon">{message.role === 'assistant' ? '●' : '●'}</span>
                <span className="label">{message.role === 'assistant' ? 'Assistant' : 'You'}</span>
                <p>{message.text}</p>
              </div>
            ))}
            {loading && (
              <div className="message assistant" role="status" aria-live="polite">
                <span className="message-icon">●</span>
                <span className="label">Assistant</span>
                <p>Assistant is thinking…</p>
              </div>
            )}
          </div>

          <div className="composer">
            <div className="composer-row">
              <textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder="Type your message here..." rows={2} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendMessage() } }} />
              <button className="send-button" type="button" onClick={sendMessage} disabled={loading || !input.trim()} aria-label="Send message">➤</button>
            </div>
            <div className="prompt-hints"><span>Example prompts:</span><button type="button" onClick={() => setInput('Add another child')}>“Add another child”</button><button type="button" onClick={() => setInput('Remove a gift')}>“Remove a gift”</button><button type="button" onClick={() => setInput('Change executor')}>“Change executor”</button></div>
          </div>
        </section>

        <aside className="panel">
          <div className="panel-header panel-title">
            <div className="title-icon">☷</div>
            <div><h2>Structured Information</h2><p>Information extracted and validated from our conversation</p></div>
          </div>
          <dl className="state-grid">
            {summary.map(([icon, label, value]) => (
              <div key={label} className="state-row">
                <div className={`field-icon ${icon}`}>{icon === 'globe' ? '◎' : icon === 'family' ? '♣' : icon === 'gift' ? '♜' : icon === 'note' ? '▤' : icon === 'shield' ? '⬟' : icon === 'home' ? '⌂' : '●'}</div><div className="field-copy"><dt>{label}</dt><dd>{value}</dd></div><span className={value !== 'Not yet provided' ? 'complete' : 'pending'}>{value !== 'Not yet provided' ? '✓' : '·'}</span>
              </div>
            ))}
          </dl>
        </aside>

        <section className="panel preview-panel">
          <div className="panel-header panel-title">
            <div className="title-icon">▤</div>
            <div><h2>Personal Wishes Document Preview</h2><p>Live preview generated from your information</p></div>
          </div>
          <div className="document-preview">
            <pre>{document || 'Loading document preview...'}</pre>
          </div>
        </section>
      </main>
    </div>
  )
}

export default App
