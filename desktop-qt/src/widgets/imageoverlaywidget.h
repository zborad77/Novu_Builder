#pragma once

#include <QImage>
#include <QPixmap>
#include <QPointF>
#include <QRectF>
#include <QString>
#include <QVector>
#include <QWidget>

#include "overlayshape.h"
#include "viewerstate.h"

class QTimer;

class ImageOverlayWidget : public QWidget
{
    Q_OBJECT

public:
    using Mode = ViewerState::Mode;

    explicit ImageOverlayWidget(QWidget *parent = nullptr);

    // Feature/view layer owns ViewerState lifetime; the widget only mutates it.
    void bindViewerState(ViewerState *viewerState);
    void refreshFromState();

    void setPhoto(const QPixmap &pixmap);
    void setPlaceholder(const QString &message);
    void setOverlayShapes(const QVector<OverlayShape> &overlayShapes);
    void setMode(Mode mode);
    void clearSelection();
    void resetView();

    QSize sizeHint() const override;

signals:
    void viewerStateChanged();
    void hoveredOverlayIdChanged(const QString &overlayId);
    void overlayActivated(const QString &overlayId, Qt::KeyboardModifiers modifiers);
    // Emitted when the user finishes a box-select drag in Mode::BoxSelect.
    // normRect is in normalized [0,1] image coordinates; may be degenerate (single click).
    // modifiers are forwarded raw — selection policy is owned entirely by the view layer.
    void boxSelectionCommitted(const QRectF &normalizedRect, Qt::KeyboardModifiers modifiers);

protected:
    void paintEvent(QPaintEvent *event) override;
    void leaveEvent(QEvent *event) override;
    void mousePressEvent(QMouseEvent *event) override;
    void mouseMoveEvent(QMouseEvent *event) override;
    void mouseReleaseEvent(QMouseEvent *event) override;
    void mouseDoubleClickEvent(QMouseEvent *event) override;
    void wheelEvent(QWheelEvent *event) override;
    void resizeEvent(QResizeEvent *event) override;
    void changeEvent(QEvent *event) override;

private:
    QRectF imageRect() const;
    QPointF toNorm(const QPoint &widgetPos) const;
    QPointF toWidget(const QPointF &norm) const;
    QPolygonF toWidgetPoly(const QVector<QPointF> &pts) const;

    void clampPan();
    void invalidateImageCache();
    void ensureImageCache();
    void buildLodPyramid();
    int  bestLodLevel() const;
    const QPixmap &bestLod();
    QString hitTestOverlayId(const QPoint &widgetPos) const;
    ViewerState &viewerState();
    const ViewerState &viewerState() const;
    void applyModeCursor();

    QPixmap m_pixmap;
    QString m_placeholder;
    QVector<OverlayShape> m_overlayShapes;

    // LOD pyramid: CPU-side halving series of the source image.
    // m_lodPixmaps[i] is the lazy GPU upload of m_lodImages[i].
    // m_lodGeneration invalidates in-flight async builds on new setPhoto().
    QVector<QImage>  m_lodImages;
    QVector<QPixmap> m_lodPixmaps;
    int              m_lodGeneration = 0;

    // Fires 120 ms after the last wheel event to trigger a smooth cache rebuild.
    QTimer *m_transformEndTimer = nullptr;

    ViewerState m_unboundViewerState;
    ViewerState *m_viewerState = &m_unboundViewerState;

    bool m_panning = false;
    QPoint m_panAnchor;
    QPointF m_panAtAnchor;

    // Image cache: widget-sized pixmap containing the scaled image at current zoom/pan.
    // Overlays are never baked in — only the image layer is cached.
    QPixmap m_imageCache;
    bool m_imageCacheValid = false;

};
