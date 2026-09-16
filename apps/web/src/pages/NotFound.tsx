import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 p-6 text-center">
      <p className="text-5xl font-semibold text-slate-700">404</p>
      <h1 className="text-lg font-semibold text-white">That page does not exist</h1>
      <p className="max-w-sm text-sm text-slate-400">
        The route you followed is not part of the command center. Head back to the overview.
      </p>
      <Link className="btn-primary" to="/">
        Go to overview
      </Link>
    </div>
  )
}
