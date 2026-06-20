import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api, { getErrorMessage } from '../api/client.js'

export default function Login() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { data } = await api.post('/api/auth/login', form)
      localStorage.setItem('token', data.token)
      localStorage.setItem('name', data.name)
      localStorage.setItem('email', data.email)
      localStorage.setItem('userId', data.userId)
      localStorage.setItem('role', data.role)
      navigate('/')
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-card">
      <h1>Giriş Yap</h1>
      <p className="muted">Belgelerine özel RAG soru-cevap paneline eriş.</p>
      {error && <div className="alert">{error}</div>}
      <form onSubmit={submit}>
        <label>E-posta</label>
        <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
        <label>Şifre</label>
        <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
        <button disabled={loading}>{loading ? 'Giriş yapılıyor...' : 'Giriş Yap'}</button>
      </form>
      <p className="muted">Hesabın yok mu? <Link to="/register">Kayıt ol</Link></p>
    </div>
  )
}
