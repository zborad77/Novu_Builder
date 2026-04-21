#include "imageoverlaywidget.h"

#include <QFutureWatcher>
#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QTimer>
#include <QWheelEvent>
#include <QtConcurrent>

namespace {
constexpr double kMinRectSize       = 0.01;
constexpr int    kVertexRadius      = 5;
constexpr int    kHintBarHeight     = 36;
constexpr double kZoomStep          = 1.15;
constexpr double kZoomMin           = 0.25;
constexpr double kZoomMax           = 10.0;
// Overlay dirty-rect margin: vertex radius + 2px anti-aliasing slop + 1px rounding guard.
constexpr int    kOverlayMarginPx   = kVertexRadius + 4;
// Pixel distance within which clicking the first vertex closes the polygon.
constexpr double kCloseThresholdPx  = 12.0;

} // namespace

// ── Construction ─────────────────────────────────────────────────────────────

ImageOverlayWidget::ImageOverlayWidget(QWidget *parent)
    : QWidget(parent)
    , m_placeholder("Vyberte zakazku a nactete fotky.")
{
    setMouseTracking(true);
    setMinimumSize(200, 200);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);

    m_transformEndTimer = new QTimer(this);
    m_transformEndTimer->setSingleShot(true);
    connect(m_transformEndTimer, &QTimer::timeout, this, [this]() {
        invalidateImageCache();
        update();
    });
}

// ── Public API ────────────────────────────────────────────────────────────────

ViewerState &ImageOverlayWidget::viewerState()
{
    return *m_viewerState;
}

const ViewerState &ImageOverlayWidget::viewerState() const
{
    return *m_viewerState;
}

void ImageOverlayWidget::applyModeCursor()
{
    if (viewerState().mode == Mode::View) {
        setCursor(m_panning ? Qt::ClosedHandCursor : Qt::OpenHandCursor);
    } else {
        setCursor(Qt::CrossCursor);
    }
    // BoxSelect and drawing modes all use CrossCursor — covered by the else branch above.
}

void ImageOverlayWidget::bindViewerState(ViewerState *viewerState)
{
    m_viewerState = viewerState ? viewerState : &m_unboundViewerState;
    refreshFromState();
}

void ImageOverlayWidget::refreshFromState()
{
    applyModeCursor();
    clampPan();
    invalidateImageCache();
    update();
}

void ImageOverlayWidget::setPhoto(const QPixmap &pixmap)
{
    m_pixmap = pixmap;
    m_placeholder.clear();
    buildLodPyramid();
    resetView();       // resets zoom/pan, clears selection, full update
}

void ImageOverlayWidget::setPlaceholder(const QString &message)
{
    m_pixmap = QPixmap();
    m_placeholder = message;
    m_lodImages.clear();
    m_lodPixmaps.clear();
    resetView();
}

void ImageOverlayWidget::setOverlayShapes(const QVector<OverlayShape> &overlayShapes)
{
    m_overlayShapes = overlayShapes;
    update();
}

void ImageOverlayWidget::setMode(Mode mode)
{
    if (viewerState().mode == mode) return;
    viewerState().mode = mode;
    clearSelection();
    applyModeCursor();
}

void ImageOverlayWidget::clearSelection()
{
    viewerState().boxSelecting   = false;
    viewerState().boxSelectStart = viewerState().boxSelectCurrent = {};
    viewerState().dragging = false;
    viewerState().hasRect  = false;
    viewerState().rectA = viewerState().rectB = {};
    viewerState().polyPts.clear();
    viewerState().polyCursor = {};
    viewerState().polyDone = false;
    update();
    emit viewerStateChanged();
}

void ImageOverlayWidget::resetView()
{
    viewerState().zoom = 1.0;
    viewerState().pan  = {};
    clearSelection();       // calls update() + viewerStateChanged
    invalidateImageCache();
}

QSize ImageOverlayWidget::sizeHint() const
{
    return QSize(640, 420);
}

// ── Coordinate helpers ────────────────────────────────────────────────────────

// Returns the image rect in widget space, accounting for zoom and pan.
// viewerState().pan is always valid (kept clamped by clampPan()), so no clamping here.
QRectF ImageOverlayWidget::imageRect() const
{
    if (m_pixmap.isNull()) return {};
    const QSizeF fit    = QSizeF(m_pixmap.size()).scaled(size(), Qt::KeepAspectRatio);
    const QSizeF zoomed = fit * viewerState().zoom;
    return QRectF(
        QPointF((width()  - zoomed.width())  / 2.0 + viewerState().pan.x(),
                (height() - zoomed.height()) / 2.0 + viewerState().pan.y()),
        zoomed);
}

QPointF ImageOverlayWidget::toNorm(const QPoint &wp) const
{
    const QRectF ir = imageRect();
    if (ir.width() <= 0 || ir.height() <= 0) return {};
    return {
        qBound(0.0, (wp.x() - ir.left()) / ir.width(),  1.0),
        qBound(0.0, (wp.y() - ir.top())  / ir.height(), 1.0)
    };
}

QPointF ImageOverlayWidget::toWidget(const QPointF &n) const
{
    const QRectF ir = imageRect();
    return {ir.left() + n.x() * ir.width(), ir.top() + n.y() * ir.height()};
}

QPolygonF ImageOverlayWidget::toWidgetPoly(const QVector<QPointF> &pts) const
{
    QPolygonF poly;
    poly.reserve(pts.size());
    for (const auto &pt : pts) poly << toWidget(pt);
    return poly;
}

QString ImageOverlayWidget::hitTestOverlayId(const QPoint &widgetPos) const
{
    for (auto it = m_overlayShapes.crbegin(); it != m_overlayShapes.crend(); ++it) {
        if (it->points.size() < 3) {
            continue;
        }

        QPainterPath path;
        path.addPolygon(toWidgetPoly(it->points));
        path.closeSubpath();
        if (path.contains(QPointF(widgetPos))) {
            return it->id;
        }
    }
    return {};
}

// Clamp viewerState().pan so the image stays anchored inside the widget.
//
// Two distinct cases per dimension:
//   zoomed ≤ widget → center (pan = 0). Allowing any non-zero pan here
//                     would displace the image off-center with no way to
//                     pull it back once zoom returns to ≤ 1.
//   zoomed > widget → allow pan in [−ex, +ex] where ex = (zoomed−widget)/2.
//                     ex is always > 0 in this branch, so qBound is safe.
//
// qMax(0.0, ex) is a rounding guard: floating-point arithmetic can
// occasionally give zoomed.width() = width() + ε for logically equal values,
// which would make ex tiny-negative and break qBound's min ≤ max precondition.
void ImageOverlayWidget::clampPan()
{
    if (m_pixmap.isNull()) { viewerState().pan = {}; return; }
    const QSizeF fit    = QSizeF(m_pixmap.size()).scaled(size(), Qt::KeepAspectRatio);
    const QSizeF zoomed = fit * viewerState().zoom;

    if (zoomed.width() <= width()) {
        viewerState().pan.setX(0.0);
    } else {
        const double ex = qMax(0.0, (zoomed.width()  - width())  / 2.0);
        viewerState().pan.setX(qBound(-ex, viewerState().pan.x(), ex));
    }
    if (zoomed.height() <= height()) {
        viewerState().pan.setY(0.0);
    } else {
        const double ey = qMax(0.0, (zoomed.height() - height()) / 2.0);
        viewerState().pan.setY(qBound(-ey, viewerState().pan.y(), ey));
    }
}

// ── LOD pyramid ───────────────────────────────────────────────────────────────

// Builds the LOD pyramid asynchronously so setPhoto() returns immediately.
//
// The halving loop runs on a thread pool worker. QPixmap cannot cross thread
// boundaries, so we convert to QImage on the main thread first, then move it
// into the lambda. The generation counter lets a new setPhoto() call invalidate
// an in-flight build: the watcher still fires but the stale result is dropped.
// Until the build completes, bestLodLevel() returns -1 → bestLod() falls back
// to m_pixmap (full resolution), so the image is visible immediately.
void ImageOverlayWidget::buildLodPyramid()
{
    m_lodImages.clear();
    m_lodPixmaps.clear();
    ++m_lodGeneration;

    if (m_pixmap.isNull()) return;

    const int generation = m_lodGeneration;
    QImage    base       = m_pixmap.toImage(); // must happen on main thread

    auto *watcher = new QFutureWatcher<QVector<QImage>>(this);
    connect(watcher, &QFutureWatcher<QVector<QImage>>::finished, this,
            [this, watcher, generation]() {
                watcher->deleteLater();
                if (generation != m_lodGeneration) return; // newer photo loaded
                m_lodImages = watcher->result();
                m_lodPixmaps.resize(m_lodImages.size()); // null QPixmaps, lazy upload
                invalidateImageCache();
                update();
            });

    watcher->setFuture(QtConcurrent::run(
        [base = std::move(base)]() mutable -> QVector<QImage> {
            QVector<QImage> lods;
            QImage img = std::move(base);
            while (qMin(img.width(), img.height()) > 256) {
                img = img.scaled(img.width() / 2, img.height() / 2,
                                 Qt::IgnoreAspectRatio, Qt::SmoothTransformation);
                lods.append(img);
            }
            return lods;
        }));
}

// Returns the largest LOD index (smallest image) whose sampled region still
// covers the physical destination pixel count, so no upscaling occurs.
// Returns -1 when the full-resolution pixmap is required (zoom ≥ 1).
int ImageOverlayWidget::bestLodLevel() const
{
    if (m_lodImages.isEmpty()) return -1;

    const QRectF ir  = imageRect();
    const QRectF vis = ir.intersected(QRectF(rect()));
    if (vis.isEmpty() || ir.width() <= 0 || ir.height() <= 0) return -1;

    const qreal dpr  = devicePixelRatioF();
    const qreal srcW = vis.width()  / ir.width()  * m_pixmap.width();
    const qreal srcH = vis.height() / ir.height() * m_pixmap.height();
    const qreal dstW = vis.width()  * dpr;
    const qreal dstH = vis.height() * dpr;

    // Iterate from coarsest to finest acceptable LOD.
    // Each level halves the image → scale = lodWidth / pixmapWidth.
    // Sampled region at that level = srcDim * scale.
    // We need sampledRegion ≥ dst to avoid upscaling artifacts.
    int best = -1;
    for (int i = 0; i < m_lodImages.size(); ++i) {
        const qreal scale = qreal(m_lodImages[i].width()) / m_pixmap.width();
        if (srcW * scale >= dstW && srcH * scale >= dstH)
            best = i;
        else
            break; // pyramid is monotone — no lower level will qualify
    }
    return best;
}

// Returns a reference to the best-fit QPixmap for the current view, uploading
// the QImage to GPU on first access for that level.
const QPixmap &ImageOverlayWidget::bestLod()
{
    const int level = bestLodLevel();
    if (level < 0) return m_pixmap;

    if (m_lodPixmaps[level].isNull())
        m_lodPixmaps[level] = QPixmap::fromImage(m_lodImages[level]);
    return m_lodPixmaps[level];
}

// ── Image cache ───────────────────────────────────────────────────────────────

void ImageOverlayWidget::invalidateImageCache()
{
    m_imageCacheValid = false;
}

// Rebuilds m_imageCache at physical pixel resolution (size × DPR).
// Setting devicePixelRatio on the cache means QPainter on it works in logical
// coordinates — no caller needs to think in physical pixels.
//
// Key difference from a naive widget-size cache:
//   - HiDPI: a 2× display gets a 2× cache → crisp rendering, not blurry.
//   - Zoom-in sharpness: we sample only the *visible* portion of the source
//     image via srcRect, not the whole pixmap. At zoom=4 we sample ¼ of the
//     image area and upscale it slightly, preserving original detail instead
//     of upscaling an already-downscaled intermediate.
void ImageOverlayWidget::ensureImageCache()
{
    if (m_imageCacheValid || m_pixmap.isNull() || size().isEmpty()) return;

    const qreal dpr      = devicePixelRatioF();
    const QSize physSize = (QSizeF(size()) * dpr).toSize();

    m_imageCache = QPixmap(physSize);
    m_imageCache.setDevicePixelRatio(dpr);
    m_imageCache.fill(QColor("#f7efe4"));

    // Compute the visible image rect (intersection of imageRect with widget bounds).
    const QRectF ir  = imageRect();
    const QRectF vis = ir.intersected(QRectF(rect()));
    if (vis.isEmpty()) { m_imageCacheValid = true; return; }

    // Pick the best-fit LOD level (smallest image whose sampled region still
    // covers the physical destination without upscaling). Falls back to the
    // original pixmap when zoom ≥ 1 or the pyramid is empty.
    const QPixmap &src = bestLod();

    // Map visible area back to source-image pixel coordinates.
    // Using src (not m_pixmap) keeps the srcRect proportional to whatever
    // LOD level was selected — the scaling arithmetic is identical.
    const QRectF srcRect(
        (vis.left()  - ir.left()) / ir.width()  * src.width(),
        (vis.top()   - ir.top())  / ir.height() * src.height(),
        vis.width()  / ir.width()  * src.width(),
        vis.height() / ir.height() * src.height());

    // QPainter on a DPR-aware QPixmap operates in logical coordinates,
    // so vis (logical rect) maps correctly to physical cache pixels.
    QPainter p(&m_imageCache);

    // SmoothPixmapTransform is expensive — only enable when:
    //   • actual scaling is happening (src ≠ dst in physical pixels)
    //   • we are not in an active pan gesture
    //   • we are not in an active zoom gesture (timer still running)
    // The timer fires 120 ms after the last wheel event and triggers a
    // smooth rebuild; until then we use nearest-neighbour for responsiveness.
    const QSizeF dstPhys(vis.size() * dpr);
    const bool scaling = (qAbs(srcRect.width()  - dstPhys.width())  > 0.5 ||
                          qAbs(srcRect.height() - dstPhys.height()) > 0.5);
    if (scaling && !m_panning && !m_transformEndTimer->isActive())
        p.setRenderHint(QPainter::SmoothPixmapTransform);

    p.drawPixmap(vis, src, srcRect);

    m_imageCacheValid = true;
}

// ── Paint ─────────────────────────────────────────────────────────────────────

void ImageOverlayWidget::paintEvent(QPaintEvent *event)
{
    QPainter p(this);
    // Clip all drawing to the dirty region so partial updates are truly partial.
    p.setClipRect(event->rect());
    p.setRenderHint(QPainter::Antialiasing);

    if (m_pixmap.isNull()) {
        p.fillRect(event->rect(), QColor("#f7efe4"));
        if (!m_placeholder.isEmpty()) {
            p.setPen(QColor("#907060"));
            p.setFont(QFont(font().family(), 12));
            p.drawText(rect(), Qt::AlignCenter, m_placeholder);
        }
        return;
    }

    // ── Image layer (from cache — 1:1 blit, no per-frame scaling) ────────────
    ensureImageCache();
    // Draw only the portion of the cache that intersects the dirty region.
    const QRect dirty = event->rect();
    p.drawPixmap(dirty.topLeft(), m_imageCache, dirty);

    // ── AI polygon ────────────────────────────────────────────────────────────
    // Build a transient QSet for O(1) lookup — never stored, never a dual source of truth.
    const QSet<QString> selectedSet(viewerState().selectedIds.begin(),
                                    viewerState().selectedIds.end());
    for (const auto &shape : m_overlayShapes) {
        if (shape.points.size() < 3) {
            continue;
        }

        const bool isSelected = (!shape.id.isEmpty() && selectedSet.contains(shape.id));
        const bool isAnchor   = (isSelected && shape.id == viewerState().anchorId);
        const bool isHovered  = (!isSelected && !shape.id.isEmpty() && shape.id == viewerState().hoveredMarkerId);

        QColor fillColor = shape.fillColor;
        QColor strokeColor = shape.strokeColor;
        int strokeWidth = 2;
        Qt::PenStyle penStyle = Qt::DashLine;

        if (isHovered) {
            fillColor.setAlpha(qMin(fillColor.alpha() + 35, 170));
            strokeColor = strokeColor.lighter(115);
            strokeWidth = 3;
        }
        if (isSelected) {
            fillColor.setAlpha(qMin(fillColor.alpha() + 55, 190));
            strokeColor = strokeColor.darker(115);
            strokeWidth = 4;
            penStyle = Qt::SolidLine;
        }

        const QPolygonF overlayPoly = toWidgetPoly(shape.points);
        QPainterPath path;
        path.addPolygon(overlayPoly);
        path.closeSubpath();
        p.fillPath(path, fillColor);
        p.setPen(QPen(strokeColor, strokeWidth, penStyle));
        p.drawPolygon(overlayPoly);

        // Primary/anchor: white focus ring drawn over the selection border.
        // The widget reads anchorId as a pure render hint; it carries no business meaning here.
        if (isAnchor) {
            p.setBrush(Qt::NoBrush);
            p.setPen(QPen(Qt::white, 1.5));
            p.drawPolygon(overlayPoly);
        }
    }

    // ── User rectangle (analysis area, Mode::Rectangle) ──────────────────────
    if (viewerState().mode == ViewerState::Mode::Rectangle
        && (viewerState().dragging || viewerState().hasRect)) {
        const QRectF r = QRectF(toWidget(viewerState().rectA),
                                toWidget(viewerState().rectB)).normalized();
        QPainterPath path;
        path.addRect(r);
        p.fillPath(path, QColor(40, 110, 220, 60));
        p.setPen(QPen(QColor(40, 110, 220), 2));
        p.drawRect(r);
    }

    // ── Box selection drag (Mode::BoxSelect) ──────────────────────────────────
    // Rendered from ViewerState; hit-testing is delegated to the view layer.
    if (viewerState().mode == ViewerState::Mode::BoxSelect && viewerState().boxSelecting) {
        const QRectF r = QRectF(toWidget(viewerState().boxSelectStart),
                                toWidget(viewerState().boxSelectCurrent)).normalized();
        QPainterPath path;
        path.addRect(r);
        p.fillPath(path, QColor(40, 110, 220, 35));
        p.setPen(QPen(QColor(40, 110, 220, 210), 1, Qt::DashLine));
        p.drawRect(r);
    }

    // ── User polygon ──────────────────────────────────────────────────────────
    if (viewerState().mode == ViewerState::Mode::Polygon && !viewerState().polyPts.isEmpty()) {
        const QPolygonF poly = toWidgetPoly(viewerState().polyPts);

        if (viewerState().polyDone) {
            QPainterPath path;
            path.addPolygon(poly);
            path.closeSubpath();
            p.fillPath(path, QColor(40, 110, 220, 60));
            p.setPen(QPen(QColor(40, 110, 220), 2));
            p.drawPolygon(poly);
        } else {
            p.setPen(QPen(QColor(40, 110, 220), 2));
            p.drawPolyline(poly);
            p.drawLine(toWidget(viewerState().polyPts.last()), toWidget(viewerState().polyCursor));
            if (viewerState().polyPts.size() >= 3) {
                p.setPen(QPen(QColor(40, 110, 220, 130), 1, Qt::DotLine));
                p.drawLine(toWidget(viewerState().polyCursor), toWidget(viewerState().polyPts.first()));
            }
        }

        // Vertex dots
        p.setBrush(QColor(40, 110, 220));
        p.setPen(Qt::NoPen);
        for (const auto &pt : viewerState().polyPts)
            p.drawEllipse(toWidget(pt), kVertexRadius, kVertexRadius);

        // Proximity ring on the first vertex: signals that a click here will
        // close the polygon instead of adding a new point.
        if (!viewerState().polyDone && viewerState().polyPts.size() >= 3) {
            const QPointF firstW = toWidget(viewerState().polyPts.first());
            if (QLineF(firstW, toWidget(viewerState().polyCursor)).length() <= kCloseThresholdPx) {
                p.setBrush(Qt::NoBrush);
                p.setPen(QPen(Qt::white, 2));
                p.drawEllipse(firstW, kVertexRadius + 4, kVertexRadius + 4);
            }
        }
    }

    // ── Instruction hint bar ──────────────────────────────────────────────────
    if (viewerState().mode != ViewerState::Mode::View && !viewerStateHasSelection(viewerState())) {
        QString hint;
        switch (viewerState().mode) {
        case ViewerState::Mode::BoxSelect:
            hint = QString::fromUtf8("Ta\u017een\u00edm obd\u00e9ln\u00edku vyberte AI detekce");
            break;
        case ViewerState::Mode::Rectangle:
            hint = "Tazenim mysi vyberte oblast opravy";
            break;
        default: // Polygon
            hint = viewerState().polyPts.isEmpty()
                ? "Kliknutim pridavejte body polygonu  \u2022  Dvojklik pro uzavreni  \u2022  Prave tl. = zrusit posledni bod"
                : QString("Body: %1  \u2022  Dvojklik pro uzavreni  \u2022  Prave tl. = zrusit posledni bod")
                    .arg(viewerState().polyPts.size());
            break;
        }

        p.fillRect(QRectF(0, height() - kHintBarHeight, width(), kHintBarHeight),
                   QColor(0, 0, 0, 120));
        p.setPen(Qt::white);
        p.setFont(QFont(font().family(), 10));
        p.drawText(
            QRectF(10, height() - kHintBarHeight, width() - 20, kHintBarHeight),
            Qt::AlignVCenter | Qt::AlignLeft, hint);
    }

    // ── Zoom indicator (shown when zoom ≠ 1) ─────────────────────────────────
    if (qAbs(viewerState().zoom - 1.0) > 0.01) {
        const QString label = QString("%1%").arg(qRound(viewerState().zoom * 100));
        p.setFont(QFont(font().family(), 9));
        const QRectF badge(width() - 52, 8, 44, 20);
        p.fillRect(badge, QColor(0, 0, 0, 110));
        p.setPen(Qt::white);
        p.drawText(badge, Qt::AlignCenter, label);
    }
}

// ── Mouse events ──────────────────────────────────────────────────────────────

void ImageOverlayWidget::leaveEvent(QEvent *event)
{
    QWidget::leaveEvent(event);
    if (!viewerState().hoveredMarkerId.isEmpty()) {
        emit hoveredOverlayIdChanged({});
    }
}

void ImageOverlayWidget::mousePressEvent(QMouseEvent *event)
{
    if (m_pixmap.isNull()) return;

    // Middle button or left drag in View mode → pan
    if (viewerState().mode == ViewerState::Mode::View && event->button() == Qt::LeftButton) {
        const QString overlayId = hitTestOverlayId(event->pos());
        if (!overlayId.isEmpty()) {
            emit overlayActivated(overlayId, event->modifiers());
            return;
        }
    }

    if (event->button() == Qt::MiddleButton
        || (viewerState().mode == ViewerState::Mode::View && event->button() == Qt::LeftButton))
    {
        m_panning      = true;
        m_panAnchor    = event->pos();
        m_panAtAnchor  = viewerState().pan;
        setCursor(Qt::ClosedHandCursor);
        return;
    }

    if (viewerState().mode == ViewerState::Mode::BoxSelect && event->button() == Qt::LeftButton) {
        viewerState().boxSelectStart   = toNorm(event->pos());
        viewerState().boxSelectCurrent = viewerState().boxSelectStart;
        viewerState().boxSelecting     = true;
        update();
        return;
    }

    if (viewerState().mode == ViewerState::Mode::Rectangle && event->button() == Qt::LeftButton) {
        viewerState().rectA = viewerState().rectB = toNorm(event->pos());
        viewerState().dragging = true;
        viewerState().hasRect  = false;
        update();
        emit viewerStateChanged();
        return;
    }

    if (viewerState().mode == ViewerState::Mode::Polygon && !viewerState().polyDone) {
        if (event->button() == Qt::LeftButton) {
            // Close by proximity: clicking within kCloseThresholdPx of the first
            // vertex (when ≥ 3 points exist) closes the polygon without adding
            // a redundant final point on top of the first one.
            if (viewerState().polyPts.size() >= 3) {
                const QPointF firstW = toWidget(viewerState().polyPts.first());
                if (QLineF(firstW, QPointF(event->pos())).length() <= kCloseThresholdPx) {
                    viewerState().polyDone = true;
                    update();
                    emit viewerStateChanged();
                    return;
                }
            }
            viewerState().polyPts.append(toNorm(event->pos()));
            update();
            emit viewerStateChanged();
        } else if (event->button() == Qt::RightButton && !viewerState().polyPts.isEmpty()) {
            viewerState().polyPts.removeLast();
            update();
            emit viewerStateChanged();
        }
    }
}

void ImageOverlayWidget::mouseMoveEvent(QMouseEvent *event)
{
    if (m_pixmap.isNull()) return;

    // ── Pan ───────────────────────────────────────────────────────────────────
    if (m_panning) {
        viewerState().pan = m_panAtAnchor + QPointF(event->pos() - m_panAnchor);
        clampPan();
        invalidateImageCache();
        update();
        emit viewerStateChanged();
        return;
    }

    // ── Box selection drag (Mode::BoxSelect) ──────────────────────────────────
    if (viewerState().mode == ViewerState::Mode::BoxSelect && viewerState().boxSelecting) {
        const QRectF oldR = QRectF(toWidget(viewerState().boxSelectStart),
                                   toWidget(viewerState().boxSelectCurrent)).normalized();
        viewerState().boxSelectCurrent = toNorm(event->pos());
        const QRectF newR = QRectF(toWidget(viewerState().boxSelectStart),
                                   toWidget(viewerState().boxSelectCurrent)).normalized();
        const QRect dirty = oldR.united(newR)
            .adjusted(-kOverlayMarginPx, -kOverlayMarginPx,
                       kOverlayMarginPx,  kOverlayMarginPx)
            .toAlignedRect();
        update(dirty);
        return;
    }

    // ── Rectangle drag — partial update ───────────────────────────────────────
    if (viewerState().mode == ViewerState::Mode::View) {
        const QString overlayId = hitTestOverlayId(event->pos());
        if (overlayId != viewerState().hoveredMarkerId) {
            emit hoveredOverlayIdChanged(overlayId);
        }
        return;
    }

    if (viewerState().mode == ViewerState::Mode::Rectangle && viewerState().dragging) {
        const QRectF oldSel = QRectF(toWidget(viewerState().rectA),
                                     toWidget(viewerState().rectB)).normalized();
        viewerState().rectB = toNorm(event->pos());
        const QRectF newSel = QRectF(toWidget(viewerState().rectA),
                                     toWidget(viewerState().rectB)).normalized();
        // Repaint only the union of the old and new selection rectangles.
        const QRect dirty = oldSel.united(newSel)
            .adjusted(-kOverlayMarginPx, -kOverlayMarginPx,
                       kOverlayMarginPx,  kOverlayMarginPx)
            .toAlignedRect();
        update(dirty);
        emit viewerStateChanged();
        return;
    }

    // ── Polygon cursor — partial update ───────────────────────────────────────
    if (viewerState().mode == ViewerState::Mode::Polygon && !viewerState().polyDone) {
        const QPointF oldW = toWidget(viewerState().polyCursor);
        viewerState().polyCursor = toNorm(event->pos());
        const QPointF newW = toWidget(viewerState().polyCursor);

        QRectF dirty;
        if (!viewerState().polyPts.isEmpty()) {
            // Bounding box of the swept live-edge (last fixed point → old/new cursor)
            const QPointF last = toWidget(viewerState().polyPts.last());
            dirty = QRectF(last, oldW).normalized()
                    .united(QRectF(last, newW).normalized());
            // Add closing-hint line region when ≥ 3 points exist
            if (viewerState().polyPts.size() >= 3) {
                const QPointF first = toWidget(viewerState().polyPts.first());
                dirty = dirty
                    .united(QRectF(first, oldW).normalized())
                    .united(QRectF(first, newW).normalized());
            }
        } else {
            // No fixed points yet: just the cursor dot area
            dirty = QRectF(oldW, QSizeF(1, 1)).united(QRectF(newW, QSizeF(1, 1)));
        }
        update(dirty.adjusted(-kOverlayMarginPx, -kOverlayMarginPx,
                               kOverlayMarginPx,  kOverlayMarginPx)
                    .toAlignedRect());
        emit viewerStateChanged();
    }
}

void ImageOverlayWidget::mouseReleaseEvent(QMouseEvent *event)
{
    if (m_panning
        && (event->button() == Qt::MiddleButton || event->button() == Qt::LeftButton))
    {
        m_panning = false;
        applyModeCursor();
        // The cache was built without SmoothPixmapTransform during the pan gesture.
        // Rebuild it now with smooth enabled for the final resting position.
        invalidateImageCache();
        update();
        return;
    }

    if (viewerState().mode == ViewerState::Mode::BoxSelect
        && viewerState().boxSelecting
        && event->button() == Qt::LeftButton) {
        viewerState().boxSelectCurrent = toNorm(event->pos());
        viewerState().boxSelecting     = false;
        const QRectF normRect = QRectF(viewerState().boxSelectStart,
                                       viewerState().boxSelectCurrent).normalized();
        viewerState().boxSelectStart = viewerState().boxSelectCurrent = {};
        update();
        // The view layer owns hit-testing and selection policy; the widget reports raw data only.
        emit boxSelectionCommitted(normRect, event->modifiers());
        return;
    }

    if (viewerState().mode == ViewerState::Mode::Rectangle
        && viewerState().dragging
        && event->button() == Qt::LeftButton) {
        viewerState().rectB    = toNorm(event->pos());
        viewerState().dragging = false;
        const QRectF r = viewerStateSelectionRect(viewerState());
        viewerState().hasRect = (r.width() > kMinRectSize && r.height() > kMinRectSize);
        update();
        emit viewerStateChanged();
    }
}

void ImageOverlayWidget::mouseDoubleClickEvent(QMouseEvent *event)
{
    if (viewerState().mode == ViewerState::Mode::View && event->button() == Qt::LeftButton) {
        resetView();
        return;
    }

    if (viewerState().mode == ViewerState::Mode::Polygon
        && !viewerState().polyDone
        && viewerState().polyPts.size() >= 3
        && event->button() == Qt::LeftButton)
    {
        viewerState().polyDone = true;
        update();
        emit viewerStateChanged();
    }
}

// ── Zoom (scroll wheel) ───────────────────────────────────────────────────────

void ImageOverlayWidget::wheelEvent(QWheelEvent *event)
{
    if (m_pixmap.isNull()) { event->ignore(); return; }

    const double factor = event->angleDelta().y() > 0 ? kZoomStep : (1.0 / kZoomStep);

    // Normalized image position under the cursor before zoom change.
    // We want this point to remain stationary after zoom.
    const QPointF cursor = event->position();
    const QRectF  ir     = imageRect();
    const QPointF normUnder(
        (cursor.x() - ir.left()) / ir.width(),
        (cursor.y() - ir.top())  / ir.height());

    viewerState().zoom = qBound(kZoomMin, viewerState().zoom * factor, kZoomMax);

    // Recompute pan so that normUnder stays at cursor position.
    // Derivation: cursor = newIr.tl + normUnder * newIr.size
    //             newIr.tl = (w - zoomed_w)/2 + pan
    //             → pan = cursor - normUnder*newZoomed - (w - newZoomed)/2
    const QSizeF fit      = QSizeF(m_pixmap.size()).scaled(size(), Qt::KeepAspectRatio);
    const QSizeF newZoomed = fit * viewerState().zoom;
    viewerState().pan.setX(cursor.x() - normUnder.x() * newZoomed.width()
                           - (width()  - newZoomed.width())  / 2.0);
    viewerState().pan.setY(cursor.y() - normUnder.y() * newZoomed.height()
                           - (height() - newZoomed.height()) / 2.0);

    clampPan();
    invalidateImageCache();
    m_transformEndTimer->start(120); // deferred smooth rebuild after gesture ends
    update();
    emit viewerStateChanged();
    event->accept();
}

// ── Resize ────────────────────────────────────────────────────────────────────

void ImageOverlayWidget::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    clampPan();
    invalidateImageCache();
    // Qt queues a repaint automatically after resize — no explicit update() needed.
}

// ── DPI change (window moved between monitors) ────────────────────────────────

void ImageOverlayWidget::changeEvent(QEvent *event)
{
    QWidget::changeEvent(event);
    if (event->type() == QEvent::DevicePixelRatioChange) {
        // Physical pixel density changed — rebuild cache at new resolution.
        invalidateImageCache();
        update();
    }
}
