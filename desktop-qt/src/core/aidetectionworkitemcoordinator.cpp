#include "aidetectionworkitemcoordinator.h"

namespace {
QString mappingSummaryForEmptySelection()
{
    return QString::fromUtf8(
        "Vyberte AI detekci pro zobrazení návazných pracovních kroků.");
}
}

AiDetectionWorkItemCoordinator::AiDetectionWorkItemCoordinator(QObject *parent)
    : QObject(parent)
{
}

void AiDetectionWorkItemCoordinator::setCaseData(const CaseDto &caseData)
{
    m_currentCaseId = caseData.id;
    m_caseData = caseData;
    recompute();
}

void AiDetectionWorkItemCoordinator::setSelectedOverlayIds(const QList<QString> &overlayIds)
{
    if (m_selectedOverlayIds == overlayIds) return;
    m_selectedOverlayIds = overlayIds;
    recompute();
}

void AiDetectionWorkItemCoordinator::reset()
{
    m_currentCaseId.clear();   // invalidates any in-flight async fetch
    m_caseData = {};
    m_selectedOverlayIds.clear();
    recompute();
}

void AiDetectionWorkItemCoordinator::recompute()
{
    QString summary = mappingSummaryForEmptySelection();
    QStringList mappedItems;
    bool highlightsProposalItems = false;

    const bool hasAiMask = m_selectedOverlayIds.contains("ai-mask");

    if (hasAiMask) {
        if (!m_caseData.proposalWorkItems.isEmpty()) {
            mappedItems = m_caseData.proposalWorkItems;
            highlightsProposalItems = true;
        } else if (!m_caseData.analysisWorkflowSteps.isEmpty()) {
            mappedItems = m_caseData.analysisWorkflowSteps;
        }

        if (mappedItems.isEmpty()) {
            summary = QString::fromUtf8(
                "AI detekce je vybraná, ale zakázka zatím nemá navazující pracovní kroky.");
        } else {
            const QString recommendedScope =
                localizeRecommendedScope(m_caseData.analysisRecommendedScope);
            summary = QString::fromUtf8("AI detekce mapuje na %1 kroků")
                          .arg(mappedItems.size());
            if (!recommendedScope.isEmpty())
                summary += QString::fromUtf8(". Doporučený rozsah: %1.").arg(recommendedScope);
            else
                summary += ".";
        }
    } else if (!m_selectedOverlayIds.isEmpty()) {
        // Non-AI selection (e.g. draft-selection or future named detections)
        summary = QString::fromUtf8(
            "Ruční výběr zatím nemá přímé AI mapování do pracovních kroků.");
    }

    emit mappingChanged(m_selectedOverlayIds, summary, mappedItems, highlightsProposalItems);
}

QString AiDetectionWorkItemCoordinator::localizeRecommendedScope(const QString &scope)
{
    if (scope == "local_repair")         return QString::fromUtf8("Lokální oprava");
    if (scope == "full_repaint")         return QString::fromUtf8("Celý nátěr");
    if (scope == "structural_repair")    return QString::fromUtf8("Strukturální oprava");
    if (scope == "full_reconstruction")  return QString::fromUtf8("Celá rekonstrukce");
    if (scope == "cleaning")             return QString::fromUtf8("Čištění");
    return scope;
}
