#pragma once

#include <QList>
#include <QPointF>
#include <QString>
#include <QVector>

#ifdef QT_DEBUG
#include <QDebug>
#endif

#include "overlayshape.h"

// Layer-C viewer state: everything the coordinator needs to save/restore
// across photo navigation, independent of the widget's render internals.
struct ViewerState {
    enum class Mode { View, BoxSelect, Rectangle, Polygon };

    Mode             mode       = Mode::View;
    double           zoom       = 1.0;
    QPointF          pan;
    QString          hoveredMarkerId;

    // Ordered multi-selection. QList is the single source of truth;
    // any QSet used for lookup is built transiently and never stored.
    QList<QString>   selectedIds;
    QString          anchorId;   // for shift-range; changes only on single/ctrl click

    // Box-select drag state (Mode::BoxSelect only).
    // Both coords are in normalized [0,1] image space.
    // Kept separate from rectA/rectB which belong to Mode::Rectangle (analysis area).
    QPointF          boxSelectStart;
    QPointF          boxSelectCurrent;
    bool             boxSelecting   = false;

    // Rectangle selection (drawn on image, for analysis area)
    QPointF          rectA, rectB;
    bool             dragging   = false;
    bool             hasRect    = false;

    // Polygon selection (drawn on image)
    QVector<QPointF> polyPts;
    QPointF          polyCursor;
    bool             polyDone   = false;

    // ── Selection helpers ─────────────────────────────────────────────────────

    void setSingleSelection(const QString &id)
    {
        selectedIds = {id};
        anchorId    = id;
    }

    // Toggle id in/out of selection.
    // Adding:   anchorId = id (anchor tracks the newly-focused item).
    // Removing: anchorId = last remaining item, or empty if nothing left.
    //           Invariant: anchorId ∈ selectedIds ∪ {""} is preserved in both branches.
    void toggleSelection(const QString &id)
    {
        const int idx = selectedIds.indexOf(id);
        if (idx != -1) {
            selectedIds.removeAt(idx);
            anchorId = selectedIds.isEmpty() ? QString{} : selectedIds.last();
        } else {
            selectedIds.append(id);
            anchorId = id;
        }
    }

    // Replace selection with the contiguous range [anchor, id] in overlay order.
    // anchor does NOT change (shift-click semantics).
    void rangeSelect(const QString &id, const QVector<OverlayShape> &shapes)
    {
        if (anchorId.isEmpty()) { setSingleSelection(id); return; }

        int anchorIdx = -1, targetIdx = -1;
        for (int i = 0; i < shapes.size(); ++i) {
            if (shapes[i].id == anchorId) anchorIdx = i;
            if (shapes[i].id == id)       targetIdx = i;
        }
        if (anchorIdx == -1 || targetIdx == -1) { setSingleSelection(id); return; }

        const int from = qMin(anchorIdx, targetIdx);
        const int to   = qMax(anchorIdx, targetIdx);
        selectedIds.clear();
        selectedIds.reserve(to - from + 1);
        for (int i = from; i <= to; ++i)
            selectedIds.append(shapes[i].id);
        // anchorId unchanged — next shift-click extends from same anchor
    }

    void clearMarkerSelection()
    {
        selectedIds.clear();
        anchorId.clear();
    }
};

// Centralized invariant guard: anchorId must always be empty or point into selectedIds.
// Call after every selection mutation (before or after normalization).
// Compiled out entirely in release builds — zero overhead in production.
inline void assertSelectionInvariant(const ViewerState &vs)
{
    Q_ASSERT(vs.anchorId.isEmpty() || vs.selectedIds.contains(vs.anchorId));
#ifdef QT_DEBUG
    qDebug() << "Selection:" << vs.selectedIds << "anchor:" << vs.anchorId;
#endif
}

inline bool viewerStateHasSelection(const ViewerState &state)
{
    if (state.mode == ViewerState::Mode::Rectangle) return state.hasRect;
    if (state.mode == ViewerState::Mode::Polygon)   return state.polyDone && state.polyPts.size() >= 3;
    return false;
}

inline QVector<QPointF> viewerStateSelectionPolygon(const ViewerState &state)
{
    if (state.mode == ViewerState::Mode::Polygon) return state.polyPts;
    if (state.mode == ViewerState::Mode::Rectangle && state.hasRect) {
        const double x0 = qMin(state.rectA.x(), state.rectB.x());
        const double y0 = qMin(state.rectA.y(), state.rectB.y());
        const double x1 = qMax(state.rectA.x(), state.rectB.x());
        const double y1 = qMax(state.rectA.y(), state.rectB.y());
        return {{x0, y0}, {x1, y0}, {x1, y1}, {x0, y1}};
    }
    return {};
}

inline QRectF viewerStateSelectionRect(const ViewerState &state)
{
    if (!state.hasRect || state.mode != ViewerState::Mode::Rectangle) return {};
    return QRectF(
        QPointF(qMin(state.rectA.x(), state.rectB.x()), qMin(state.rectA.y(), state.rectB.y())),
        QPointF(qMax(state.rectA.x(), state.rectB.x()), qMax(state.rectA.y(), state.rectB.y())));
}
