import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api, { getErrorMessage } from '../api/client.js'

export default function Dashboard() {
  const [documents, setDocuments] = useState([])
  const [file, setFile] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)

  const loadDocuments = async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get('/api/documents')
      setDocuments(data)
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadDocuments()
  }, [])

  const upload = async (e) => {
    e.preventDefault()
    if (!file) return

    const formData = new FormData()
    formData.append('file', file)
    setUploading(true)
    setError('')

    try {
      await api.post('/api/documents/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      setFile(null)
      e.target.reset()
      await loadDocuments()
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setUploading(false)
    }
  }

  const remove = async (id) => {
    if (!confirm('Bu belgeyi silmek istiyor musun?')) return
    try {
      await api.delete(`/api/documents/${id}`)
      await loadDocuments()
    } catch (err) {
      setError(getErrorMessage(err))
    }
  }

  return (
    <div>
      <section className="hero">
        <h1>Özel Belgeler İçin RAG AI Platformu</h1>
        <p>PDF, DOCX veya TXT belgelerini yükle; sadece belge içeriğine dayalı kaynaklı cevaplar al.</p>
      </section>

      <section className="panel">
        <h2>Belge Yükle</h2>
        <form className="upload-form" onSubmit={upload}>
          <input type="file" accept=".pdf,.docx,.txt" onChange={(e) => setFile(e.target.files?.[0])} />
          <button disabled={!file || uploading}>{uploading ? 'İşleniyor...' : 'Yükle ve İşle'}</button>
        </form>
        <p className="muted">İlk model indirmesinde işlem birkaç dakika sürebilir.</p>
      </section>

      {error && <div className="alert">{error}</div>}

      <section className="panel">
        <div className="section-title">
          <h2>Belgelerim</h2>
          <button className="secondary" onClick={loadDocuments}>Yenile</button>
        </div>
        {loading ? <p>Yükleniyor...</p> : null}
        {!loading && documents.length === 0 ? <p className="muted">Henüz belge yüklenmedi.</p> : null}
        <div className="doc-grid">
          {documents.map((doc) => (
            <article className="doc-card" key={doc.id}>
              <div>
                <h3>{doc.originalFilename}</h3>
                <p className="muted">Chunk: {doc.chunkCount ?? '-'} · Boyut: {formatBytes(doc.fileSize)}</p>
              </div>
              <span className={`badge ${doc.status?.toLowerCase()}`}>{doc.status}</span>
              {doc.errorMessage && <p className="error-text">{doc.errorMessage}</p>}
              <div className="card-actions">
                <Link className={doc.status === 'READY' ? 'button-link' : 'button-link disabled'} to={doc.status === 'READY' ? `/documents/${doc.id}/chat` : '#'}>Sohbet</Link>
                <button className="danger" onClick={() => remove(doc.id)}>Sil</button>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}

function formatBytes(bytes) {
  if (!bytes) return '-'
  const units = ['B', 'KB', 'MB', 'GB']
  let size = bytes
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit++
  }
  return `${size.toFixed(1)} ${units[unit]}`
}
