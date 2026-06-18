import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api, { getErrorMessage } from '../api/client.js'

export default function Register() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { data } = await api.post('/api/auth/register', form)
      localStorage.setItem('token', data.token)
      localStorage.setItem('name', data.name)
      localStorage.setItem('email', data.email)
      navigate('/')
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-card">
      <h1>Kayıt Ol</h1>
      <p className="muted">Kendi özel belge analiz alanını oluştur.</p>
      {error && <div className="alert">{error}</div>}
      <form onSubmit={submit}>
        <label>Ad Soyad</label>
        <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
        <label>E-posta</label>
        <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
        <label>Şifre</label>
        <input type="password" minLength="6" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
        <button disabled={loading}>{loading ? 'Kayıt oluşturuluyor...' : 'Kayıt Ol'}</button>
      </form>
      <p className="muted">Zaten hesabın var mı? <Link to="/login">Giriş yap</Link></p>
    </div>
  )
}
