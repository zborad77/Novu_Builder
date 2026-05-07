#pragma once

#include <QPixmap>
#include <QPointF>
#include <QRectF>
#include <QString>
#include <QVector>
#include <QWidget>

class ImageOverlayWidget : public QWidget
{
    Q_OBJECT

public:
    enum class Mode { View, Rectangle, Polygon };

    explicit ImageOverlayWidget(QWidget *parent = nullptr);

    void setPhoto(const QPixmap &pixmap);
    void setPlaceholder(const QString &message);
    void setAiPolygon(const QVector<QPointF> &normalizedPoints);
    void setMode(Mode mode);
    void clearSelection();

    bool hasSelection() const;
    QVector<QPointF> selectionPolygon() const; // normalized [0..1] coords
    QRectF selectionRect() const;              // normalized [0..1]

    QSize sizeHint() const override;

signals:
    void selectionChanged();

protected:
    void paintEvent(QPaintEvent *event) override;
    void mousePressEvent(QMouseEvent *event) override;
    void mouseMoveEvent(QMouseEvent *event) override;
    void mouseReleaseEvent(QMouseEvent *event) override;
    void mouseDoubleClickEvent(QMouseEvent *event) override;

private:
    QRectF photoRect() const;
    QPointF toNorm(const QPoint &widgetPos) const;
    QPointF toWidget(const QPointF &norm) const;
    QPolygonF toWidgetPoly(const QVector<QPointF> &pts) const;

    QPixmap m_pixmap;
    QString m_placeholder;
    QVector<QPointF> m_aiPolygon;
    Mode m_mode = Mode::View;

    // Rectangle state
    QPointF m_rectA, m_rectB;
    bool m_dragging = false;
    bool m_hasRect = false;

    // Polygon state
    QVector<QPointF> m_polyPts;
    QPointF m_polyCursor;
    bool m_polyDone = false;
};
