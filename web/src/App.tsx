import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { Navigate, RouterProvider, createBrowserRouter } from "react-router"
import { AppShell } from "@/components/layout/AppShell"
import { TooltipProvider } from "@/components/ui/tooltip"
import { Toaster } from "@/components/ui/sonner"
import { LoginPage } from "@/pages/LoginPage"
import { NewSearchPage } from "@/pages/NewSearchPage"
import { Placeholder } from "@/pages/Placeholder"
import { RunPage } from "@/pages/RunPage"
import { RunsPage } from "@/pages/RunsPage"

const queryClient = new QueryClient()

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: <AppShell />,
    children: [
      { path: "/", element: <Navigate to="/search" replace /> },
      { path: "/search", element: <NewSearchPage /> },
      { path: "/runs", element: <RunsPage /> },
      { path: "/runs/:jobId", element: <RunPage /> },
      { path: "/runs/:jobId/candidates/:candidateId", element: <Placeholder title="Candidate" /> },
      { path: "/settings", element: <Placeholder title="Settings" /> },
    ],
  },
])

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <RouterProvider router={router} />
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  )
}