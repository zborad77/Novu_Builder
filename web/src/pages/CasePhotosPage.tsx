import { Link, useParams } from '@tanstack/react-router'
import { usePhotos } from 'features/cases/api/caseQueries'

export function CasePhotosPage() {
  const { caseId } = useParams({ strict: false })
  const { data, isLoading, isError } = usePhotos(caseId ?? '')

  if (!caseId) return null

  if (isLoading) {
    return (
      <section className="rounded-[2rem] border border-slate-200/80 bg-white/90 p-6 shadow-sm">
        <div className="mb-4 h-4 w-24 animate-pulse rounded bg-slate-200" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="aspect-square animate-pulse rounded-2xl bg-slate-200" />
          ))}
        </div>
      </section>
    )
  }

  if (isError) {
    return (
      <section className="rounded-[2rem] border border-red-100 bg-red-50 p-6">
        <p className="text-sm text-red-600">Failed to load photos.</p>
      </section>
    )
  }

  const photos = data?.items ?? []
  const meta = data?.meta

  if (photos.length === 0) {
    return (
      <section className="rounded-[2rem] border border-slate-200/80 bg-white/90 p-10 shadow-sm">
        <p className="text-center text-sm text-slate-500">No photos uploaded yet.</p>
      </section>
    )
  }

  return (
    <section className="rounded-[2rem] border border-slate-200/80 bg-white/90 p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">
          Photos
        </h2>
        <span className="text-sm text-slate-500">
          {photos.length} photo{photos.length !== 1 ? 's' : ''}
        </span>
      </div>

      {meta && !meta.hasMinimumCount && (
        <div className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3">
          <p className="text-sm text-amber-800">
            At least {meta.minimumRecommendedCount} photos recommended for analysis.{' '}
            {meta.minimumRecommendedCount - photos.length} more needed.
          </p>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        {photos.map((photo) => {
          const thumb = photo.variants.preview.url ?? photo.url
          return (
            <Link
              key={photo.id}
              to="/cases/$caseId/photos/$imageId"
              params={{ caseId, imageId: photo.id }}
              className="group relative block overflow-hidden rounded-2xl border border-slate-200 bg-slate-100 transition hover:border-emerald-300 hover:shadow-md"
            >
              <div className="aspect-square">
                <img
                  src={thumb}
                  alt={photo.originalFilename}
                  className="h-full w-full object-cover transition group-hover:scale-105"
                  loading="lazy"
                />
              </div>
              {(photo.isPrimary || photo.isAnalysisReference) && (
                <div className="absolute bottom-0 left-0 right-0 flex flex-wrap gap-1 p-2">
                  {photo.isPrimary && (
                    <span className="rounded-full bg-emerald-600/90 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white backdrop-blur">
                      Primary
                    </span>
                  )}
                  {photo.isAnalysisReference && (
                    <span className="rounded-full bg-violet-600/90 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white backdrop-blur">
                      Analysis
                    </span>
                  )}
                </div>
              )}
            </Link>
          )
        })}
      </div>
    </section>
  )
}
