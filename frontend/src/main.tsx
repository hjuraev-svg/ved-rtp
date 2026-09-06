import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
import { AuthProvider, LiveProvider, ToastProvider } from './store'

const saved = localStorage.getItem('ved_theme')
if (saved) document.documentElement.dataset.theme = saved

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ToastProvider>
      <AuthProvider>
        <LiveProvider>
          <App />
        </LiveProvider>
      </AuthProvider>
    </ToastProvider>
  </React.StrictMode>,
)
