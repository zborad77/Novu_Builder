import React from 'react'
import ReactDOM from 'react-dom/client'
import { RouterProvider } from '@tanstack/react-router'
import { AuthProvider } from 'app/providers/AuthProvider'
import { QueryProvider } from 'app/providers/QueryProvider'
import { ToastProvider } from 'app/providers/ToastProvider'
import { router } from 'app/router'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryProvider>
      <AuthProvider>
        <ToastProvider>
          <RouterProvider router={router} />
        </ToastProvider>
      </AuthProvider>
    </QueryProvider>
  </React.StrictMode>,
)
