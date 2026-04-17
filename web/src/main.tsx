import React from 'react'
import ReactDOM from 'react-dom/client'
import { RouterProvider } from '@tanstack/react-router'
import { AuthProvider } from 'app/providers/AuthProvider'
import { ImpersonationProvider } from 'app/providers/ImpersonationProvider'
import { QueryProvider } from 'app/providers/QueryProvider'
import { ToastProvider } from 'app/providers/ToastProvider'
import { router } from 'app/router'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryProvider>
      <AuthProvider>
        <ImpersonationProvider>
          <ToastProvider>
            <RouterProvider router={router} />
          </ToastProvider>
        </ImpersonationProvider>
      </AuthProvider>
    </QueryProvider>
  </React.StrictMode>,
)
