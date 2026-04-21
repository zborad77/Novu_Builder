#pragma once

#include <QColor>
#include <QPointF>
#include <QString>
#include <QVector>

// Semantic category of an overlay projection. Assigned in rebuildOverlayShapes().
// The widget never reads this — it is used only in the view/summary layer.
enum class OverlayKind {
    AiDetection,       // AI-detected damage polygon  ("ai-mask")
    ConfirmedWorkItem, // confirmed proposal work item (reserved, not yet projected)
    ManualMarker,      // user-placed discrete marker  (reserved, not yet projected)
    DraftSelection,    // user-drawn area (rect/poly)  ("draft-selection")
};

struct OverlayShape {
    QString         id;
    QString         label;
    OverlayKind     kind        = OverlayKind::ManualMarker;
    QVector<QPointF> points;
    QColor          fillColor   = QColor(230, 120, 30, 55);
    QColor          strokeColor = QColor(230, 120, 30, 200);
};
