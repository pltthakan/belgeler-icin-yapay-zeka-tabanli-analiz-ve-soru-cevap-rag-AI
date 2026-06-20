import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api, { getErrorMessage } from '../api/client.js'

export default function Admin() {
  const [departments, setDepartments] = useState([])
  const [users, setUsers] = useState([])
  const [auditLogs, setAuditLogs] = useState([])
  const [traces, setTraces] = useState([])
  const [departmentName, setDepartmentName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const [departmentRes, userRes, auditRes, traceRes] = await Promise.all([
        api.get('/api/admin/departments'),
        api.get('/api/admin/users'),
        api.get('/api/admin/audit-logs'),
        api.get('/api/admin/llm-traces')
      ])
      setDepartments(departmentRes.data)
      setUsers(userRes.data)
      setAuditLogs(auditRes.data)
      setTraces(traceRes.data)
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const createDepartment = async (event) => {
    event.preventDefault()
    if (!departmentName.trim()) return
    try {
      await api.post('/api/admin/departments', { name: departmentName.trim() })
      setDepartmentName('')
      await load()
    } catch (err) {
      setError(getErrorMessage(err))
    }
  }

  const updateAccess = async (user, field, value) => {
    const role = field === 'role' ? value : user.role
    const departmentId = field === 'departmentId'
      ? (value ? Number(value) : null)
      : user.departmentId
    try {
      await api.put(`/api/admin/users/${user.id}/access`, { role, departmentId })
      await load()
    } catch (err) {
      setError(getErrorMessage(err))
    }
  }

  return (
    <div>
      <Link to="/" className="back-link">← Belgelere dön</Link>
      <section className="hero">
        <h1>Yönetim ve gözlemlenebilirlik</h1>
        <p>Departman erişimi, kullanıcı rolleri, audit kayıtları ve RAG/LLM çalışma izleri yalnızca yöneticiler tarafından görüntülenir.</p>
      </section>

      {error && <div className="alert">{error}</div>}

      <section className="panel">
        <div className="section-title"><h2>Departmanlar</h2><button className="secondary" onClick={load}>Yenile</button></div>
        <form className="inline-form" onSubmit={createDepartment}>
          <input value={departmentName} onChange={(event) => setDepartmentName(event.target.value)} placeholder="Örn. Mühendislik" />
          <button>Departman ekle</button>
        </form>
        <p className="muted">{departments.length ? departments.map((department) => department.name).join(' · ') : 'Henüz departman eklenmedi.'}</p>
      </section>

      <section className="panel">
        <h2>Kullanıcı erişimi</h2>
        {loading ? <p>Yükleniyor...</p> : (
          <div className="table-scroll">
            <table>
              <thead><tr><th>Kullanıcı</th><th>Rol</th><th>Departman</th></tr></thead>
              <tbody>{users.map((user) => (
                <tr key={user.id}>
                  <td>{user.name}<br /><span className="muted">{user.email}</span></td>
                  <td><select value={user.role} onChange={(event) => updateAccess(user, 'role', event.target.value)}>
                    <option value="EMPLOYEE">Çalışan</option><option value="MANAGER">Yönetici</option><option value="ADMIN">Admin</option>
                  </select></td>
                  <td><select value={user.departmentId || ''} onChange={(event) => updateAccess(user, 'departmentId', event.target.value)}>
                    <option value="">Atanmamış</option>
                    {departments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}
                  </select></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel">
        <h2>Audit kayıtları</h2>
        <p className="muted">Son 100 kayıt gösterilir. Silinen belgelerde de belge kimliği korunur.</p>
        <div className="log-list">{auditLogs.map((log) => (
          <details className="log-entry" key={log.id}>
            <summary><strong>{log.action}</strong> · {log.actorEmail} · belge #{log.documentId ?? '-'} <span className="muted">{formatDate(log.createdAt)}</span></summary>
            <pre>{log.details}</pre>
          </details>
        ))}</div>
      </section>

      <section className="panel">
        <h2>LLM/RAG çalışma izleri</h2>
        <p className="muted">Her kayıtta sağlayıcı, model, seçilen kaynaklar, prompt, yanıt, süre ve hata bilgisi saklanır. Bu alan belge verisi içerebilir.</p>
        <div className="log-list">{traces.map((trace) => (
          <details className="log-entry" key={trace.id}>
            <summary><strong>{trace.provider || 'bilinmiyor'}</strong> · {trace.model || 'model yok'} · belge #{trace.documentId} · {trace.durationMs ?? '-'} ms <span className="muted">{formatDate(trace.createdAt)}</span></summary>
            <p><strong>Mod:</strong> {trace.responseMode || '-'}</p>
            {trace.error && <p className="error-text">{trace.error}</p>}
            {trace.prompt && <><strong>Prompt</strong><pre>{trace.prompt}</pre></>}
            <strong>Seçilen chunk’lar</strong><pre>{trace.retrievedChunksJson}</pre>
            {trace.answer && <><strong>Yanıt</strong><pre>{trace.answer}</pre></>}
          </details>
        ))}</div>
      </section>
    </div>
  )
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString('tr-TR') : ''
}
