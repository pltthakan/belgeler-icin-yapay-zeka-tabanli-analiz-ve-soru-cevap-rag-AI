import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import api, { getErrorMessage } from '../api/client.js'

export default function Chat() {
  const { id } = useParams()
  const [document, setDocument] = useState(null)
  const [messages, setMessages] = useState([])
  const [question, setQuestion] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  const load = async () => {
    setError('')
    try {
      const [docRes, historyRes] = await Promise.all([
        api.get(`/api/documents/${id}`),
        api.get(`/api/chat/documents/${id}/history`)
      ])
      setDocument(docRes.data)
      setMessages(historyRes.data)
    } catch (err) {
      setError(getErrorMessage(err))
    }
  }

  useEffect(() => {
    load()
  }, [id])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const submit = async (e) => {
    e.preventDefault()
    if (!question.trim()) return
    setLoading(true)
    setError('')
    try {
      const { data } = await api.post(`/api/chat/documents/${id}/ask`, { question })
      setMessages((prev) => [...prev, data])
      setQuestion('')
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <Link to="/" className="back-link">← Belgelerime dön</Link>
      <section className="chat-header">
        <h1>{document?.originalFilename || 'Belge sohbeti'}</h1>
        <p className="muted">Sorular sadece seçili belge kaynaklarına göre cevaplanır.</p>
      </section>

      {error && <div className="alert">{error}</div>}

      <section className="chat-box">
        {messages.length === 0 && (
          <div className="empty-chat">
            <p>Bu belgeyle ilgili ilk sorunu sor.</p>
            <span>Örnek: “Bu belgenin ana konusu nedir?”</span>
          </div>
        )}
        {messages.map((message) => (
          <div className="message" key={message.id}>
            <div className="question"><strong>Sen:</strong> {message.question}</div>
            <div className="answer"><strong>AI:</strong><br />{message.answer}</div>
            {message.sources?.length > 0 && (
              <details className="sources">
                <summary>Kaynak parçaları göster</summary>
                {message.sources.map((source, idx) => (
                  <div className="source" key={idx}>
                    <div className="source-meta">Sayfa {source.pageNumber ?? '-'} · Chunk {source.chunkIndex} · Skor {Number(source.score).toFixed(3)}</div>
                    <p>{source.text}</p>
                  </div>
                ))}
              </details>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </section>

      <form className="ask-form" onSubmit={submit}>
        <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Belge hakkında soru sor..." />
        <button disabled={loading || !question.trim()}>{loading ? 'Cevaplanıyor...' : 'Sor'}</button>
      </form>
    </div>
  )
}
