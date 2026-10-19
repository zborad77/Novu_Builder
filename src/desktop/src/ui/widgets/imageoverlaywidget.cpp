#include "imageoverlaywidget.h"

#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>

namespace {
constexpr double kMinRectSize = 0.01; // minimum normalized selection size
constexpr int    kVertexRadius = 5;
constexpr int    kHintBarHeight = 36;
} // namespace

ImageOverlayWidget::ImageOverlayWidget(QWidget *parent)
    : QWidget(parent)
    , m_placeholder("Vyberte zakazku a nactete fotky.")
{
    setMouseTracking(true);
    setMinimumSize(200, 200);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
}

void ImageOverlayWidget::setPhoto(const QPixmap &pixmap)
{
    m_pixmap = pixmap;
    m_placeholder.clear();
    clearSelection();
    update();
}

void ImageOverlayWidget::setPlaceholder(const QString &message)
{
    m_pixmap = QPixmap();
    m_placeholder = message;
    clearSelection();
    update();
}

void ImageOverlayWidget::setAiPolygon(const QVector<QPointF> &normalizedPoints)
{
    m_aiPolygon = normalizedPoints;
    update();
}

void ImageOverlayWidget::setMode(Mode mode)
{
    if (m_mode == mode) return;
    m_mode = mode;
    clearSelection();
    setCursor(mode == Mode::View ? Qt::ArrowCursor : Qt::CrossCursor);
}

void ImageOverlayWidget::clearSelection()
{
    m_dragging = false;
    m_hasRect = false;
    m_rectA = m_rectB = {};
    m_polyPts.clear();
    m_polyDone = false;
    update();
    emit selectionChanged();
}

bool ImageOverlayWidget::hasSelection() const
{
    if (m_mode == Mode::Rectangle) return m_hasRect;
    if (m_mode == Mode::Polygon)   return m_polyDone && m_polyPts.size() >= 3;
    return false;
}

QVector<QPointF> ImageOverlayWidget::selectionPolygon() const
{
    if (m_mode == Mode::Polygon) return m_polyPts;
    if (m_mode == Mode::Rectangle && m_hasRect) {
        const double x0 = qMin(m_rectA.x(), m_rectB.x());
        const double y0 = qMin(m_rectA.y(), m_rectB.y());
        const double x1 = qMax(m_rectA.x(), m_rectB.x());
        const double y1 = qMax(m_rectA.y(), m_rectB.y());
        return {{x0, y0}, {x1, y0}, {x1, y1}, {x0, y1}};
    }
    return {};
}

QRectF ImageOverlayWidget::selectionRect() const
{
    if (!m_hasRect || m_mode != Mode::Rectangle) return {};
    return QRectF(
        QPointF(qMin(m_rectA.x(), m_rectB.x()), qMin(m_rectA.y(), m_rectB.y())),
        QPointF(qMax(m_rectA.x(), m_rectB.x()), qMax(m_rectA.y(), m_rectB.y())));
}

QSize ImageOverlayWidget::sizeHint() const
{
    return QSize(640, 420);
}

// ── Private helpers ──────────────────────────────────────────────────────────

QRectF ImageOverlayWidget::photoRect() const
{
    if (m_pixmap.isNull()) return QRectF(rect());
    const QSizeF scaled = m_pixmap.size().scaled(size(), Qt::KeepAspectRatio);
    const QPointF tl(
        (width()  - scaled.width())  / 2.0,
        (height() - scaled.height()) / 2.0);
    return QRectF(tl, scaled);
}

QPointF ImageOverlayWidget::toNorm(const QPoint &wp) const
{
    const QRectF pr = photoRect();
    if (pr.width() <= 0 || pr.height() <= 0) return {};
    return {
        qBound(0.0, (wp.x() - pr.left()) / pr.width(),  1.0),
        qBound(0.0, (wp.y() - pr.top())  / pr.height(), 1.0)
    };
}

QPointF ImageOverlayWidget::toWidget(const QPointF &n) const
{
    const QRectF pr = photoRect();
    return {pr.left() + n.x() * pr.width(), pr.top() + n.y() * pr.height()};
}

QPolygonF ImageOverlayWidget::toWidgetPoly(const QVector<QPointF> &pts) const
{
    QPolygonF poly;
    poly.reserve(pts.size());
    for (const auto &pt : pts) poly << toWidget(pt);
    return poly;
}

// ── Paint ────────────────────────────────────────────────────────────────────

void ImageOverlayWidget::paintEvent(QPaintEvent *)
{
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing);
    p.setRenderHint(QPainter::SmoothPixmapTransform);

    // Background
    p.fillRect(rect(), QColor("#f7efe4"));

    if (m_pixmap.isNull()) {
        p.setPen(QColor("#907060"));
        p.setFont(QFont(font().family(), 12));
        p.drawText(rect(), Qt::AlignCenter, m_placeholder);
        return;
    }

    // Photo (letterboxed)
    const QRectF pr = photoRect();
    p.drawPixmap(pr.toRect(), m_pixmap);

    // ── AI polygon — semi-transparent orange ──────────────────────────────
    if (!m_aiPolygon.isEmpty()) {
        const QPolygonF aiPoly = toWidgetPoly(m_aiPolygon);
        QPainterPath path;
        path.addPolygon(aiPoly);
        path.closeSubpath();
        p.fillPath(path, QColor(230, 120, 30, 55));
        p.setPen(QPen(QColor(230, 120, 30, 200), 2, Qt::DashLine));
        p.drawPolygon(aiPoly);
    }

    // ── User rectangle ────────────────────────────────────────────────────
    if (m_mode == Mode::Rectangle && (m_dragging || m_hasRect)) {
        const QRectF r = QRectF(toWidget(m_rectA), toWidget(m_rectB)).normalized();
        QPainterPath path;
        path.addRect(r);
        p.fillPath(path, QColor(40, 110, 220, 60));
        p.setPen(QPen(QColor(40, 110, 220), 2));
        p.drawRect(r);
    }

    // ── User polygon ──────────────────────────────────────────────────────
    if (m_mode == Mode::Polygon && !m_polyPts.isEmpty()) {
        const QPolygonF poly = toWidgetPoly(m_polyPts);

        if (m_polyDone) {
            // Closed filled polygon
            QPainterPath path;
            path.addPolygon(poly);
            path.closeSubpath();
            p.fillPath(path, QColor(40, 110, 220, 60));
            p.setPen(QPen(QColor(40, 110, 220), 2));
            p.drawPolygon(poly);
        } else {
            // In-progress: open polyline + live edge to cursor
            p.setPen(QPen(QColor(40, 110, 220), 2));
            p.drawPolyline(poly);
            // Live edge from last point to cursor
            p.drawLine(toWidget(m_polyPts.last()), toWidget(m_polyCursor));
            // Closing hint (dashed) from cursor back to first point
            if (m_polyPts.size() >= 3) {
                p.setPen(QPen(QColor(40, 110, 220, 130), 1, Qt::DotLine));
                p.drawLine(toWidget(m_polyCursor), toWidget(m_polyPts.first()));
            }
        }

        // Vertex dots
        p.setBrush(QColor(40, 110, 220));
        p.setPen(Qt::NoPen);
        for (const auto &pt : m_polyPts) {
            p.drawEllipse(toWidget(pt), kVertexRadius, kVertexRadius);
        }
    }

    // ── Instruction hint bar ──────────────────────────────────────────────
    if (m_mode != Mode::View && !hasSelection()) {
        const bool isRect = (m_mode == Mode::Rectangle);
        const QString hint = isRect
            ? "Tazenim mysi vyberte oblast opravy"
            : (m_polyPts.isEmpty()
                ? "Kliknutim pridavejte body polygonu  \u2022  Dvojklik pro uzavreni  \u2022  Prave tl. = zrusit posledni bod"
                : QString("Body: %1  \u2022  Dvojklik pro uzavreni  \u2022  Prave tl. = zrusit posledni bod")
                    .arg(m_polyPts.size()));

        p.fillRect(QRectF(0, height() - kHintBarHeight, width(), kHintBarHeight),
                   QColor(0, 0, 0, 120));
        p.setPen(Qt::white);
        p.setFont(QFont(font().family(), 10));
        p.drawText(
            QRectF(10, height() - kHintBarHeight, width() - 20, kHintBarHeight),
            Qt::AlignVCenter | Qt::AlignLeft, hint);
    }
}

// ── Mouse events ─────────────────────────────────────────────────────────────

void ImageOverlayWidget::mousePressEvent(QMouseEvent *event)
{
    if (m_pixmap.isNull()) return;

    if (m_mode == Mode::Rectangle) {
        if (event->button() == Qt::LeftButton) {
            m_rectA = m_rectB = toNorm(event->pos());
            m_dragging = true;
            m_hasRect = false;
            update();
        }
    } else if (m_mode == Mode::Polygon && !m_polyDone) {
        if (event->button() == Qt::LeftButton) {
            m_polyPts.append(toNorm(event->pos()));
            update();
            emit selectionChanged();
        } else if (event->button() == Qt::RightButton && !m_polyPts.isEmpty()) {
            m_polyPts.removeLast();
            update();
            emit selectionChanged();
        }
    }
}

void ImageOverlayWidget::mouseMoveEvent(QMouseEvent *event)
{
    if (m_pixmap.isNull()) return;

    if (m_mode == Mode::Rectangle && m_dragging) {
        m_rectB = toNorm(event->pos());
        update();
    } else if (m_mode == Mode::Polygon && !m_polyDone) {
        m_polyCursor = toNorm(event->pos());
        update();
    }
}

void ImageOverlayWidget::mouseReleaseEvent(QMouseEvent *event)
{
    if (m_mode == Mode::Rectangle && m_dragging && event->button() == Qt::LeftButton) {
        m_rectB = toNorm(event->pos());
        m_dragging = false;
        const QRectF r = selectionRect();
        m_hasRect = (r.width() > kMinRectSize && r.height() > kMinRectSize);
        update();
        if (m_hasRect) emit selectionChanged();
    }
}

void ImageOverlayWidget::mouseDoubleClickEvent(QMouseEvent *event)
{
    if (m_mode == Mode::Polygon
        && !m_polyDone
        && m_polyPts.size() >= 3
        && event->button() == Qt::LeftButton)
    {
        m_polyDone = true;
        update();
        emit selectionChanged();
    }
}
