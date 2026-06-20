import { Link, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import Dashboard from './pages/Dashboard.jsx'
import Login from './pages/Login.jsx'
import Register from './pages/Register.jsx'
import Chat from './pages/Chat.jsx'
import Admin from './pages/Admin.jsx'

function Layout({ children }) {
  const navigate = useNavigate()
  const token = localStorage.getItem('token')
  const userName = localStorage.getItem('name')
  const role = localStorage.getItem('role')

  const logout = () => {
    localStorage.clear()
    navigate('/login')
  }

  return (
    <div>
      <header className="topbar">
        <Link to="/" className="brand">Private Document RAG AI</Link>
        <nav>
          {token ? (
            <>
              <span className="user">{userName}</span>
              {role === 'ADMIN' && <Link to="/admin">Yönetim</Link>}
              <button className="ghost" onClick={logout}>Çıkış</button>
            </>
          ) : (
            <>
              <Link to="/login">Giriş</Link>
              <Link to="/register">Kayıt</Link>
            </>
          )}
        </nav>
      </header>
      <main className="container">{children}</main>
    </div>
  )
}

function PrivateRoute({ children }) {
  const token = localStorage.getItem('token')
  if (!token) return <Navigate to="/login" replace />
  return children
}

function AdminRoute({ children }) {
  if (localStorage.getItem('role') !== 'ADMIN') return <Navigate to="/" replace />
  return children
}

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/" element={<PrivateRoute><Dashboard /></PrivateRoute>} />
        <Route path="/documents/:id/chat" element={<PrivateRoute><Chat /></PrivateRoute>} />
        <Route path="/admin" element={<PrivateRoute><AdminRoute><Admin /></AdminRoute></PrivateRoute>} />
      </Routes>
    </Layout>
  )
}
