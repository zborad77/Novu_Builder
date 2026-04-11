#include "casedetailview.h"

#include <algorithm>
#include <array>
#include <cmath>

#include <QApplication>
#include <QBuffer>
#include <QDialog>
#include <QDialogButtonBox>
#include <QDoubleValidator>
#include <QPainter>
#include <QStyledItemDelegate>
#include <QDesktopServices>
#include <QDir>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcess>
#include <QFormLayout>
#include <QFrame>
#include <QHBoxLayout>
#include <QIcon>
#include <QImage>
#include <QImageReader>
#include <QImageWriter>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QMessageBox>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QResizeEvent>
#include <QScrollArea>
#include <QStandardPaths>
#include <QStringList>
#include <QSignalBlocker>
#include <QSizePolicy>
#include <QTabWidget>
#include <QTimer>
#include <QVBoxLayout>

#include "services/apiservice.h"
#include "viewmodels/casedetailviewmodel.h"

class NoFocusRectDelegate : public QStyledItemDelegate
{
public:
    using QStyledItemDelegate::QStyledItemDelegate;
    void paint(QPainter *painter, const QStyleOptionViewItem &option,
               const QModelIndex &index) const override
    {
        QStyleOptionViewItem opt = option;
        opt.state &= ~QStyle::State_HasFocus;
        QStyledItemDelegate::paint(painter, opt, index);
    }
};

namespace {
constexpr int kPreparedImageMaxEdge = 1600;
constexpr int kPreparedImageQuality = 85;
constexpr int kImagePollingIntervalMs = 1500;
constexpr int kImagePollingAttemptLimit = 8;

QString formatMaterialItem(const CaseDto::ProposalMaterialItem &item)
{
    QString label = item.name;
    if (!item.unit.isEmpty()) {
        label += QString::fromUtf8(" \u2014 %1 %2 \u00d7 %3 CZK")
            .arg(item.quantity, 0, 'f', 2)
            .arg(item.unit)
            .arg(item.unitPrice, 0, 'f', 2);
    }
    label += QString::fromUtf8(" = %1 CZK").arg(item.totalPrice, 0, 'f', 2);
    return label;
}

QString localizeRepairScope(const QString &scope)
{
    if (scope == "local_repair")      return QString::fromUtf8("Lok\u00e1ln\u00ed oprava");
    if (scope == "full_repaint")      return QString::fromUtf8("Cel\u00fd n\u00e1t\u011br");
    if (scope == "structural_repair") return QString::fromUtf8("Strukturaln\u00ed oprava");
    if (scope == "full_reconstruction") return QString::fromUtf8("Cel\u00e1 rekonstrukce");
    if (scope == "cleaning")          return QString::fromUtf8("\u010ci\u0161t\u011bn\u00ed");
    return scope;
}

QString localizeObjectType(const QString &type)
{
    if (type == "facade")  return QString::fromUtf8("Fas\u00e1da");
    if (type == "roof")    return QString::fromUtf8("St\u0159echa");
    if (type == "floor")   return QString::fromUtf8("Podlaha");
    if (type == "wall")    return QString::fromUtf8("Ze\u010f");
    if (type == "ceiling") return QString::fromUtf8("Strop");
    return type;
}

QString localizeSurfaceCondition(const QString &cond)
{
    if (cond == "requires_attention") return QString::fromUtf8("Vy\u017eaduje pozornost");
    if (cond == "good")               return QString::fromUtf8("Dobr\u00fd stav");
    if (cond == "critical")           return QString::fromUtf8("Kritick\u00fd stav");
    if (cond == "moderate")           return QString::fromUtf8("St\u0159edn\u00ed stav");
    return cond;
}

QString localizeRecommendedScope(const QString &scope)
{
    return localizeRepairScope(scope);
}

QString localizeBlockingReason(const QString &reason)
{
    if (reason.contains("Final proposal has not been created"))
        return QString::fromUtf8("Fin\u00e1ln\u00ed verze nab\u00eddky nebyla je\u0161t\u011b vytvo\u0159ena.");
    if (reason.contains("not enough photos") || reason.contains("No photos"))
        return QString::fromUtf8("Nedostatek fotek pro anal\u00fdzu.");
    if (reason.contains("analysis") && reason.contains("not"))
        return QString::fromUtf8("AI anal\u00fdza nebyla dokon\u010dena.");
    if (reason.contains("draft") && reason.contains("not"))
        return QString::fromUtf8("N\u00e1vrh nebyl p\u0159ipraven.");
    return reason;
}

QString serverProcessingStatusLabel(const QString &status)
{
    if (status == "ready") {
        return "pripraveno";
    }
    if (status == "uploaded") {
        return "nahrano";
    }
    if (status == "processing") {
        return "zpracovava se";
    }
    if (status == "failed") {
        return "chyba zpracovani";
    }
    return status.isEmpty() ? "neznamy stav" : status;
}

QString analysisWorkflowStatusLabel(const QString &status)
{
    if (status == "waiting_for_photos") {
        return "ceka na fotky";
    }
    if (status == "processing_photos") {
        return "zpracovava fotky";
    }
    if (status == "awaiting_more_photos") {
        return "ceka na dalsi fotky";
    }
    if (status == "ready") {
        return "navrh pripraven";
    }
    return status.isEmpty() ? "-" : status;
}

QString draftWorkflowStatusLabel(const QString &status)
{
    if (status == "missing") {
        return "navrh chybi";
    }
    if (status == "waiting_for_photos") {
        return "ceka na fotky";
    }
    if (status == "processing_photos") {
        return "zpracovava fotky";
    }
    if (status == "awaiting_more_photos") {
        return "ceka na dalsi fotky";
    }
    if (status == "ready") {
        return "navrh pripraven";
    }
    return status.isEmpty() ? "-" : status;
}

QString finalProposalStatusLabel(const QString &status)
{
    if (status == "ready_for_export") {
        return "pripraveno pro export";
    }
    return status.isEmpty() ? "zatim nevytvoreno" : status;
}

QString workflowSummaryLabel(const CaseDto &caseDto)
{
    QStringList parts;
    if (!caseDto.workflowAnalysisStatus.isEmpty()) {
        parts << QString("fotky: %1").arg(analysisWorkflowStatusLabel(caseDto.workflowAnalysisStatus));
    }
    if (!caseDto.workflowDraftStatus.isEmpty()) {
        parts << QString("navrh: %1").arg(draftWorkflowStatusLabel(caseDto.workflowDraftStatus));
    }
    if (!caseDto.workflowFinalProposalStatus.isEmpty()) {
        parts << QString("final: %1").arg(finalProposalStatusLabel(caseDto.workflowFinalProposalStatus));
    }
    return parts.isEmpty() ? "-" : parts.join(" | ");
}

QString workflowBlockingReasonsLabel(const QStringList &blockingReasons)
{
    if (blockingReasons.isEmpty()) {
        return "bez aktivnich blokaci";
    }

    QStringList renderedReasons;
    renderedReasons.reserve(blockingReasons.size());
    for (const auto &reason : blockingReasons) {
        if (!reason.trimmed().isEmpty()) {
            renderedReasons << QString::fromUtf8("\u2022 ") + localizeBlockingReason(reason.trimmed());
        }
    }

    return renderedReasons.isEmpty() ? "bez aktivnich blokaci" : renderedReasons.join("\n");
}

QString summarizeServerImageStatuses(const std::vector<ImageDto> &images)
{
    if (images.empty()) {
        return {};
    }

    int readyCount = 0;
    int processingCount = 0;
    int failedCount = 0;
    int otherCount = 0;

    for (const auto &image : images) {
        if (image.processingStatus == "ready") {
            ++readyCount;
        } else if (image.processingStatus == "processing" || image.processingStatus == "uploaded") {
            ++processingCount;
        } else if (image.processingStatus == "failed") {
            ++failedCount;
        } else {
            ++otherCount;
        }
    }

    QStringList parts;
    if (readyCount > 0) {
        parts << QString("%1 pripravenych").arg(readyCount);
    }
    if (processingCount > 0) {
        parts << QString("%1 ve zpracovani").arg(processingCount);
    }
    if (failedCount > 0) {
        parts << QString("%1 s chybou").arg(failedCount);
    }
    if (otherCount > 0) {
        parts << QString("%1 v jinem stavu").arg(otherCount);
    }
    return parts.join(", ");
}

bool hasPendingServerImageStatuses(const std::vector<ImageDto> &images)
{
    return std::any_of(images.begin(), images.end(), [](const ImageDto &image) {
        return image.processingStatus != "ready" && image.processingStatus != "failed";
    });
}

QSize scaledImageSize(const QSize &sourceSize, int maxEdge)
{
    if (sourceSize.width() <= 0 || sourceSize.height() <= 0) {
        return {};
    }

    const int currentMaxEdge = std::max(sourceSize.width(), sourceSize.height());
    if (currentMaxEdge <= maxEdge) {
        return sourceSize;
    }

    const double scale = static_cast<double>(maxEdge) / static_cast<double>(currentMaxEdge);
    return QSize(
        std::max(1, static_cast<int>(std::lround(sourceSize.width() * scale))),
        std::max(1, static_cast<int>(std::lround(sourceSize.height() * scale))));
}

QString formatDecimalForEdit(const QString &currencyLabel)
{
    QString normalized = currencyLabel;
    normalized.remove("CZK", Qt::CaseInsensitive);
    normalized = normalized.trimmed();
    normalized.replace(",", ".");
    return normalized;
}

double readDoubleFromEdit(QLineEdit *edit)
{
    if (!edit) {
        return 0.0;
    }

    bool isNumber = false;
    const auto value = edit->text().trimmed().replace(",", ".").toDouble(&isNumber);
    return isNumber ? value : 0.0;
}

QString matchLabel(const QString &expected, const QString &actual)
{
    if (expected.isEmpty()) {
        return {};
    }
    if (actual.isEmpty()) {
        return QString("ceka na vyhodnoceni (%1)").arg(expected);
    }
    if (expected.compare(actual, Qt::CaseInsensitive) == 0) {
        return QString("shoda (%1)").arg(actual);
    }
    return QString("neshoda, ocekavano %1, aktualne %2").arg(expected, actual);
}

QStringList expectedWorkItemKeywords(const QString &expectedScope)
{
    const auto normalized = expectedScope.toLower();
    if (normalized.contains("strech")) {
        return {"prohlidka strechy", "cisteni krytiny", "ochranneho nateru"};
    }
    if (normalized.contains("fasad")) {
        return {"prohlidka fasady", "myti", "finalni nater"};
    }
    if (normalized.contains("vrat")) {
        return {"prohlidka objektu", "priprava podkladu", "dokoncovaci"};
    }
    if (normalized.contains("zdi")) {
        return {"prohlidka objektu", "priprava podkladu", "dokoncovaci"};
    }
    return {};
}

QString proposalWorkItemsMatchLabel(const QString &expectedScope, const QStringList &proposalWorkItems)
{
    const auto keywords = expectedWorkItemKeywords(expectedScope);
    if (keywords.isEmpty()) {
        return {};
    }
    if (proposalWorkItems.isEmpty()) {
        return "ceka na navrh";
    }

    int matchedKeywords = 0;
    for (const auto &keyword : keywords) {
        const bool found = std::any_of(proposalWorkItems.begin(), proposalWorkItems.end(), [&keyword](const QString &item) {
            return item.toLower().contains(keyword);
        });
        if (found) {
            ++matchedKeywords;
        }
    }

    if (matchedKeywords == keywords.size()) {
        return "zakladni shoda";
    }
    if (matchedKeywords > 0) {
        return QString("castecna shoda (%1/%2)").arg(matchedKeywords).arg(keywords.size());
    }
    return "bez shody";
}

QStringList expectedMaterialKeywords(const QString &expectedScope)
{
    const auto normalized = expectedScope.toLower();
    if (normalized.contains("strech")) {
        return {"cistic strech", "biocidni ochrana", "stresni nater"};
    }
    if (normalized.contains("fasad")) {
        return {"fasadni penetrace", "fasadni barva", "opravna"};
    }
    if (normalized.contains("vrat")) {
        return {"zakladni cistic", "univerzalni penetrace", "povrchovy material"};
    }
    if (normalized.contains("zdi")) {
        return {"zakladni cistic", "univerzalni penetrace", "povrchovy material"};
    }
    return {};
}

QString proposalMaterialsMatchLabel(const QString &expectedScope, const QStringList &proposalMaterials)
{
    const auto keywords = expectedMaterialKeywords(expectedScope);
    if (keywords.isEmpty()) {
        return {};
    }
    if (proposalMaterials.isEmpty()) {
        return "ceka na navrh";
    }

    int matchedKeywords = 0;
    for (const auto &keyword : keywords) {
        const bool found = std::any_of(proposalMaterials.begin(), proposalMaterials.end(), [&keyword](const QString &item) {
            return item.toLower().contains(keyword);
        });
        if (found) {
            ++matchedKeywords;
        }
    }

    if (matchedKeywords == keywords.size()) {
        return "zakladni shoda";
    }
    if (matchedKeywords > 0) {
        return QString("castecna shoda (%1/%2)").arg(matchedKeywords).arg(keywords.size());
    }
    return "bez shody";
}

int exactMatchScore(const QString &expected, const QString &actual)
{
    if (expected.isEmpty()) {
        return -1;
    }
    if (actual.isEmpty()) {
        return 1;
    }
    return expected.compare(actual, Qt::CaseInsensitive) == 0 ? 2 : 0;
}

int keywordMatchScore(const QStringList &keywords, const QStringList &items)
{
    if (keywords.isEmpty()) {
        return -1;
    }
    if (items.isEmpty()) {
        return 1;
    }

    int matchedKeywords = 0;
    for (const auto &keyword : keywords) {
        const bool found = std::any_of(items.begin(), items.end(), [&keyword](const QString &item) {
            return item.toLower().contains(keyword);
        });
        if (found) {
            ++matchedKeywords;
        }
    }

    if (matchedKeywords == keywords.size()) {
        return 2;
    }
    if (matchedKeywords > 0) {
        return 1;
    }
    return 0;
}

QString overallReferenceTestStatus(
    const QString &expectedScope,
    const QString &actualScope,
    const QString &expectedPrimaryFilename,
    const QString &actualPrimaryFilename,
    const QString &expectedAnalysisReferenceFilename,
    const QString &actualAnalysisReferenceFilename,
    const QStringList &proposalWorkItems,
    const QStringList &proposalMaterials)
{
    const std::array<int, 5> scores = {
        exactMatchScore(expectedScope, actualScope),
        exactMatchScore(expectedPrimaryFilename, actualPrimaryFilename),
        exactMatchScore(expectedAnalysisReferenceFilename, actualAnalysisReferenceFilename),
        keywordMatchScore(expectedWorkItemKeywords(expectedScope), proposalWorkItems),
        keywordMatchScore(expectedMaterialKeywords(expectedScope), proposalMaterials),
    };

    int considered = 0;
    int passed = 0;
    int partial = 0;
    int failed = 0;
    for (const auto score : scores) {
        if (score < 0) {
            continue;
        }
        ++considered;
        if (score == 2) {
            ++passed;
        } else if (score == 1) {
            ++partial;
        } else {
            ++failed;
        }
    }

    if (considered == 0) {
        return {};
    }
    if (failed == 0 && partial == 0) {
        return "test prosel";
    }
    if (passed > 0 || partial > 0) {
        return "castecne";
    }
    return "potrebuje kontrolu";
}
}

CaseDetailView::CaseDetailView(QWidget *parent)
    : QWidget(parent)
{
    auto *rootLayout = new QVBoxLayout(this);
    rootLayout->setContentsMargins(0, 0, 0, 0);

    auto *card = new QFrame(this);
    card->setObjectName("detailCard");
    auto *cardLayout = new QVBoxLayout(card);
    cardLayout->setContentsMargins(20, 16, 20, 20);
    cardLayout->setSpacing(10);

    // ── Always-visible header ────────────────────────────────────────────────
    m_errorLabel = new QLabel(card);
    m_errorLabel->setObjectName("errorLabel");
    m_errorLabel->setWordWrap(true);
    m_errorLabel->hide();

    m_titleLabel = new QLabel("Vyber zakazku ze seznamu", card);
    m_titleLabel->setObjectName("sectionTitle");

    m_subtitleLabel = new QLabel("Po vyberu zakazky v levem panelu se zde nacte jeji detail.", card);
    m_subtitleLabel->setObjectName("hintLabel");
    m_subtitleLabel->setWordWrap(true);

    cardLayout->addWidget(m_errorLabel);
    cardLayout->addWidget(m_titleLabel);
    cardLayout->addWidget(m_subtitleLabel);

    // ── Read-only banner ──────────────────────────────────────────────────────
    m_readOnlyBanner = new QLabel(
        QString::fromUtf8("Tato zak\u00e1zka je dokon\u010dena. Pro \u00fapravy klikn\u011bte na Editovat."),
        card);
    m_readOnlyBanner->setObjectName("readOnlyBanner");
    m_readOnlyBanner->setWordWrap(true);
    m_editUnlockButton = new QPushButton(QString::fromUtf8("Editovat"), card);
    m_editUnlockButton->setObjectName("editUnlockButton");
    m_readOnlyBanner->hide();
    m_editUnlockButton->hide();
    cardLayout->addWidget(m_readOnlyBanner);
    cardLayout->addWidget(m_editUnlockButton);

    connect(m_editUnlockButton, &QPushButton::clicked, this, [this]() {
        setReadOnly(false);
    });

    // ── Tab widget ────────────────────────────────────────────────────────────
    m_tabWidget = new QTabWidget(card);
    m_tabWidget->setObjectName("detailTabs");
    m_tabWidget->setWhatsThis(QString::fromUtf8(
        "Z\u00e1lo\u017eky zak\u00e1zky:\n"
        "\u2022 P\u0159ehled \u2014 souhrn AI anal\u00fdzy a cen\n"
        "\u2022 Fotky \u2014 spr\u00e1va fotek\n"
        "\u2022 Anal\u00fdza \u2014 v\u00fdsledky AI (jen desktop)\n"
        "\u2022 Nab\u00eddka \u2014 editace nab\u00eddky\n"
        "\u2022 V\u00fdstup zak\u00e1zky \u2014 export a odesl\u00e1n\u00ed"));
    cardLayout->addWidget(m_tabWidget, 1);

    // Helper: creates a scrollable page and registers it as a tab
    auto makeScrollPage = [](QTabWidget *tabs, const QString &label) -> QVBoxLayout * {
        auto *scroll = new QScrollArea(tabs);
        scroll->setWidgetResizable(true);
        scroll->setFrameShape(QFrame::NoFrame);
        scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        auto *page = new QWidget();
        page->setObjectName("tabPage");
        auto *pageLayout = new QVBoxLayout(page);
        pageLayout->setContentsMargins(4, 12, 4, 20);
        pageLayout->setSpacing(16);
        scroll->setWidget(page);
        tabs->addTab(scroll, label);
        return pageLayout;
    };

    // ════════════════════════════════════════════════════════════════════════
    // TAB 1 — Přehled (Dashboard)
    // ════════════════════════════════════════════════════════════════════════
    auto *overviewLayout = makeScrollPage(m_tabWidget, "Prehled");

    // ── Info strip ────────────────────────────────────────────────────────
    auto *overviewCard = new QFrame();
    overviewCard->setObjectName("summaryCard");
    auto *overviewForm = new QFormLayout(overviewCard);
    overviewForm->setContentsMargins(16, 12, 16, 12);
    overviewForm->setVerticalSpacing(8);
    overviewForm->setHorizontalSpacing(16);
    m_statusValueLabel = new QLabel("-", overviewCard);
    m_addressValueLabel = new QLabel("-", overviewCard);
    m_addressValueLabel->setWordWrap(true);
    m_scopeValueLabel = new QLabel("-", overviewCard);
    m_areaValueLabel = new QLabel("-", overviewCard);
    m_workflowStatusValueLabel = new QLabel("-", overviewCard);
    m_workflowStatusValueLabel->setWordWrap(true);
    m_workflowBlockingReasonsValueLabel = new QLabel("bez aktivnich blokaci", overviewCard);
    m_workflowBlockingReasonsValueLabel->setWordWrap(true);
    m_referenceTestContextLabel = new QLabel(overviewCard);
    m_referenceTestContextLabel->setWordWrap(true);
    m_referenceTestContextLabel->hide();
    overviewForm->addRow("Stav", m_statusValueLabel);
    overviewForm->addRow("Adresa", m_addressValueLabel);
    overviewForm->addRow(QString::fromUtf8("Typ opravy"), m_scopeValueLabel);
    overviewForm->addRow("Plocha", m_areaValueLabel);
    overviewForm->addRow("Workflow", m_workflowStatusValueLabel);
    overviewForm->addRow("Blokace", m_workflowBlockingReasonsValueLabel);
    overviewForm->addRow("Test", m_referenceTestContextLabel);

    // ── Primary photo ─────────────────────────────────────────────────────
    m_dashPhotoLabel = new QLabel();
    m_dashPhotoLabel->setObjectName("dashPhoto");
    m_dashPhotoLabel->setFixedHeight(280);
    m_dashPhotoLabel->setAlignment(Qt::AlignCenter);
    m_dashPhotoLabel->setText(QString::fromUtf8("Vyberte zak\u00e1zku pro zobrazen\u00ed hlavn\u00ed fotografie."));
    m_dashPhotoLabel->setCursor(Qt::PointingHandCursor);
    m_dashPhotoLabel->installEventFilter(this);

    // ── 2-column row: Analysis + Pricing ─────────────────────────────────
    auto *columnsWidget = new QWidget();
    auto *columnsLayout = new QHBoxLayout(columnsWidget);
    columnsLayout->setContentsMargins(0, 0, 0, 0);
    columnsLayout->setSpacing(12);

    auto *analysisCard = new QFrame();
    analysisCard->setObjectName("detailCard");
    auto *analysisCardLayout = new QVBoxLayout(analysisCard);
    analysisCardLayout->setContentsMargins(16, 16, 16, 16);
    analysisCardLayout->setSpacing(8);
    auto *analysisTitle = new QLabel(QString::fromUtf8("AI Anal\u00fdza"));
    analysisTitle->setObjectName("subSectionTitle");
    auto *analysisForm = new QFormLayout();
    analysisForm->setVerticalSpacing(8);
    analysisForm->setHorizontalSpacing(12);
    m_dashObjTypeLabel = new QLabel("-");
    m_dashAreaLabel = new QLabel("-");
    m_dashSurfaceLabel = new QLabel("-");
    m_dashScopeLabel = new QLabel("-");
    m_dashDurationLabel = new QLabel("-");
    analysisForm->addRow(QString::fromUtf8("Typ objektu:"), m_dashObjTypeLabel);
    analysisForm->addRow(QString::fromUtf8("Plocha (odhad):"), m_dashAreaLabel);
    analysisForm->addRow(QString::fromUtf8("Stav povrchu:"), m_dashSurfaceLabel);
    analysisForm->addRow(QString::fromUtf8("Doporu\u010den\u00fd rozsah:"), m_dashScopeLabel);
    analysisForm->addRow(QString::fromUtf8("Odhad trv\u00e1n\u00ed:"), m_dashDurationLabel);
    analysisCardLayout->addWidget(analysisTitle);
    analysisCardLayout->addLayout(analysisForm);
    analysisCardLayout->addStretch();

    auto *pricingCard = new QFrame();
    pricingCard->setObjectName("detailCard");
    auto *pricingCardLayout = new QVBoxLayout(pricingCard);
    pricingCardLayout->setContentsMargins(16, 16, 16, 16);
    pricingCardLayout->setSpacing(8);
    auto *pricingTitle = new QLabel(QString::fromUtf8("Cenov\u00fd souhrn"));
    pricingTitle->setObjectName("subSectionTitle");
    auto *pricingForm = new QFormLayout();
    pricingForm->setVerticalSpacing(8);
    pricingForm->setHorizontalSpacing(12);
    m_dashLaborLabel = new QLabel("-");
    m_dashMaterialLabel = new QLabel("-");
    m_dashTransportLabel = new QLabel("-");
    m_dashMarginLabel = new QLabel("-");
    m_dashTotalLabel = new QLabel("-");
    m_dashTotalLabel->setObjectName("dashTotal");
    pricingForm->addRow(QString::fromUtf8("Cena pr\u00e1ce:"), m_dashLaborLabel);
    pricingForm->addRow(QString::fromUtf8("Cena materi\u00e1lu:"), m_dashMaterialLabel);
    pricingForm->addRow("Doprava:", m_dashTransportLabel);
    pricingForm->addRow(QString::fromUtf8("Mar\u017ee:"), m_dashMarginLabel);
    auto *totalSep = new QFrame();
    totalSep->setFrameShape(QFrame::HLine);
    auto *totalRow = new QHBoxLayout();
    auto *totalKey = new QLabel(QString::fromUtf8("CELKEM v\u010d. DPH:"));
    totalKey->setObjectName("dashTotalKey");
    totalRow->addWidget(totalKey);
    totalRow->addWidget(m_dashTotalLabel);
    totalRow->addStretch();
    pricingCardLayout->addWidget(pricingTitle);
    pricingCardLayout->addLayout(pricingForm);
    pricingCardLayout->addWidget(totalSep);
    pricingCardLayout->addLayout(totalRow);
    pricingCardLayout->addStretch();

    columnsLayout->addWidget(analysisCard, 1);
    columnsLayout->addWidget(pricingCard, 1);

    // ── Technologický postup ──────────────────────────────────────────────
    auto *workflowDashCard = new QFrame();
    workflowDashCard->setObjectName("detailCard");
    auto *workflowDashLayout = new QVBoxLayout(workflowDashCard);
    workflowDashLayout->setContentsMargins(16, 16, 16, 16);
    workflowDashLayout->setSpacing(10);
    auto *workflowDashTitle = new QLabel(QString::fromUtf8("Technologick\u00fd postup pr\u00e1ce"));
    workflowDashTitle->setObjectName("subSectionTitle");
    m_dashWorkflowList = new QListWidget();
    m_dashWorkflowList->setObjectName("workflowList");
    m_dashWorkflowList->setMaximumHeight(170);
    m_dashWorkflowList->setFocusPolicy(Qt::NoFocus);
    m_dashWorkflowList->setItemDelegate(new NoFocusRectDelegate(m_dashWorkflowList));
    m_dashWorkflowList->addItem(QString::fromUtf8("Postup pr\u00e1ce bude k dispozici po dokon\u010den\u00ed anal\u00fdzy."));
    workflowDashLayout->addWidget(workflowDashTitle);
    workflowDashLayout->addWidget(m_dashWorkflowList);

    // ── Akce ─────────────────────────────────────────────────────────────
    auto *actionsCard = new QFrame();
    actionsCard->setObjectName("detailCard");
    auto *actionsRowLayout = new QHBoxLayout(actionsCard);
    actionsRowLayout->setContentsMargins(16, 12, 16, 12);
    actionsRowLayout->setSpacing(10);
    m_dashRunAnalysisButton = new QPushButton(QString::fromUtf8("Spustit AI anal\u00fdzu"));
    m_dashRunAnalysisButton->setEnabled(false);
    m_dashRunAnalysisButton->setWhatsThis(QString::fromUtf8("Odešle fotky na server a spust\u00ed AI anal\u00fdzu. Server automaticky zjist\u00ed plochu, doporu\u010d\u00ed materi\u00e1ly a postup pr\u00e1ce."));
    actionsRowLayout->addWidget(m_dashRunAnalysisButton);
    actionsRowLayout->addStretch();

    overviewLayout->addWidget(overviewCard);
    overviewLayout->addWidget(m_dashPhotoLabel);
    overviewLayout->addWidget(columnsWidget);
    overviewLayout->addWidget(workflowDashCard);
    overviewLayout->addStretch();
    actionsCard->hide(); // Spustit analýzu patří jen do záložky Analýza

    // ════════════════════════════════════════════════════════════════════════
    // TAB 2 — Fotky
    // ════════════════════════════════════════════════════════════════════════
    auto *photosLayout = makeScrollPage(m_tabWidget, "Fotky");

    m_primaryImageLabel = new QLabel("Hlavni fotka pro analyzu: -");
    m_primaryImageLabel->setObjectName("primaryImageLabel");
    m_overlayWidget = new ImageOverlayWidget();
    m_overlayWidget->setMinimumHeight(400);
    m_overlayWidget->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
    m_imageHintLabel = new QLabel("Nactete zakazku pro zobrazeni fotek.");
    m_imageHintLabel->setObjectName("hintLabel");
    m_imageHintLabel->setWordWrap(true);

    // Overlay selection mode controls
    auto *overlayModeLabel = new QLabel("Oblast opravy:");
    overlayModeLabel->setObjectName("hintLabel");
    m_overlayModeViewButton = new QPushButton("Prohlizet");
    m_overlayModeViewButton->setCheckable(true);
    m_overlayModeViewButton->setChecked(true);
    m_overlayModeViewButton->setObjectName("overlayModeBtn");
    m_overlayModeViewButton->setWhatsThis(QString::fromUtf8("Prohlíže\u010dí re\u017eim \u2014 m\u016f\u017eete proch\u00e1zet fotky bez kreslen\u00ed oblasti."));
    m_overlayModeRectButton = new QPushButton("Obdelnik");
    m_overlayModeRectButton->setCheckable(true);
    m_overlayModeRectButton->setObjectName("overlayModeBtn");
    m_overlayModeRectButton->setWhatsThis(QString::fromUtf8("Nakreslete obd\u00e9ln\u00edk kolem oblasti opravy. Po nakreslen\u00ed klikn\u011bte na Ulo\u017eit."));
    m_overlayModePolyButton = new QPushButton("Polygon");
    m_overlayModePolyButton->setCheckable(true);
    m_overlayModePolyButton->setObjectName("overlayModeBtn");
    m_overlayModePolyButton->setWhatsThis(QString::fromUtf8("Nakreslete polygon kolem nepravideln\u00e9 oblasti opravy. Klikn\u011bte pro ka\u017ed\u00fd bod, dvouklikem ukon\u010d\u00edte."));
    m_overlayConfirmButton = new QPushButton("Ulozit vyber oblasti");
    m_overlayConfirmButton->setEnabled(false);
    m_overlayConfirmButton->setWhatsThis(QString::fromUtf8("Ulo\u017e\u00ed nakreslenou oblast na server. Oblast bude pou\u017eita p\u0159i AI anal\u00fdze pro p\u0159esn\u011bj\u0161\u00ed v\u00fdpo\u010det plochy."));
    m_overlayAreaEdit = new QLineEdit();
    m_overlayAreaEdit->setPlaceholderText("Upresnena plocha (m\u00B2) \u2014 volitelne");
    m_overlayAreaEdit->setMaximumWidth(220);
    auto *overlayControlsRow = new QHBoxLayout();
    overlayControlsRow->setSpacing(8);
    overlayControlsRow->addWidget(overlayModeLabel);
    overlayControlsRow->addWidget(m_overlayModeViewButton);
    overlayControlsRow->addWidget(m_overlayModeRectButton);
    overlayControlsRow->addWidget(m_overlayModePolyButton);
    overlayControlsRow->addStretch();
    overlayControlsRow->addWidget(m_overlayAreaEdit);
    overlayControlsRow->addWidget(m_overlayConfirmButton);

    auto *imageActionsLayout = new QHBoxLayout();
    imageActionsLayout->setSpacing(10);
    m_moveUpButton = new QPushButton(QStringLiteral("\u25C0"));
    m_moveUpButton->setEnabled(false);
    m_moveDownButton = new QPushButton(QStringLiteral("\u25B6"));
    m_moveDownButton->setEnabled(false);
    m_moveUpButton->setObjectName("imageNavButton");
    m_moveDownButton->setObjectName("imageNavButton");
    m_moveUpButton->setMinimumSize(40, 40);
    m_moveDownButton->setMinimumSize(40, 40);
    m_moveUpButton->setMaximumSize(40, 40);
    m_moveDownButton->setMaximumSize(40, 40);
    m_setPrimaryButton = new QPushButton("Nastavit jako hlavni");
    m_setPrimaryButton->setEnabled(false);
    m_setPrimaryButton->setVisible(false);
    m_setAnalysisReferenceButton = new QPushButton("Pouzit pro analyzu");
    m_setAnalysisReferenceButton->setEnabled(false);
    m_setAnalysisReferenceButton->setVisible(false);
    imageActionsLayout->addWidget(m_moveUpButton);
    imageActionsLayout->addWidget(m_moveDownButton);
    imageActionsLayout->addStretch();
    imageActionsLayout->addWidget(m_setPrimaryButton);
    imageActionsLayout->addWidget(m_setAnalysisReferenceButton);

    m_thumbnailScrollArea = new QScrollArea();
    m_thumbnailScrollArea->setObjectName("thumbnailScrollArea");
    m_thumbnailScrollArea->setWidgetResizable(false);
    m_thumbnailScrollArea->setFrameShape(QFrame::NoFrame);
    m_thumbnailScrollArea->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    m_thumbnailScrollArea->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    m_thumbnailScrollArea->setMinimumHeight(164);
    m_thumbnailScrollArea->setMaximumHeight(164);
    m_thumbnailStripWidget = new QWidget(m_thumbnailScrollArea);
    m_thumbnailStripWidget->setObjectName("thumbnailStripWidget");
    m_thumbnailStripLayout = new QHBoxLayout(m_thumbnailStripWidget);
    m_thumbnailStripLayout->setContentsMargins(12, 12, 12, 12);
    m_thumbnailStripLayout->setSpacing(12);
    m_thumbnailScrollArea->setWidget(m_thumbnailStripWidget);

    auto *pcUploadTitle = new QLabel(QString::fromUtf8("P\u0159idat dal\u0161\u00ed fotografie z po\u010d\u00edta\u010de"));
    pcUploadTitle->setObjectName("subSectionTitle");
    auto *pcUploadHintLabel = new QLabel(
        "Alternativni vstup \xe2\x80\x94 pouzijte pokud neni k dispozici mobilni aplikace nebo pro zpracovani archivnich zakazek.");
    pcUploadHintLabel->setObjectName("hintLabel");
    pcUploadHintLabel->setWordWrap(true);
    m_pendingLocalImagesLabel = new QLabel("Vybrane fotky z PC: zatim zadne.");
    m_pendingLocalImagesLabel->setObjectName("hintLabel");
    m_pendingLocalImagesLabel->setWordWrap(true);
    m_pendingLocalImagesList = new QListWidget();
    m_pendingLocalImagesList->setObjectName("detailList");
    m_pendingLocalImagesList->setMaximumHeight(120);
    m_pendingLocalImagesList->setFocusPolicy(Qt::NoFocus);
    m_pendingLocalImagesList->setItemDelegate(new NoFocusRectDelegate(m_pendingLocalImagesList));
    m_pendingLocalImagesList->setVisible(false);
    auto *pcUploadActionsLayout = new QHBoxLayout();
    pcUploadActionsLayout->setSpacing(10);
    m_addImagesButton = new QPushButton("Vybrat fotografie z disku");
    m_addImagesButton->setWhatsThis(QString::fromUtf8("Otev\u0159e dialog pro v\u00fdb\u011br fotek z va\u0161eho po\u010d\u00edta\u010de. M\u016f\u017eete vybrat v\u00edce fotek najednou."));
    m_convertImagesButton = new QPushButton(QString::fromUtf8("P\u0159ipravit fotky"));
    m_convertImagesButton->setEnabled(false);
    m_convertImagesButton->setWhatsThis(QString::fromUtf8("Zkomprimuje a p\u0159iprav\u00ed vybran\u00e9 fotky pro nahr\u00e1n\u00ed na server (zmen\u0161\u00ed velikost soubor\u016f)."));
    pcUploadActionsLayout->addWidget(m_addImagesButton);
    pcUploadActionsLayout->addWidget(m_convertImagesButton);
    pcUploadActionsLayout->addStretch();

    photosLayout->addWidget(m_primaryImageLabel);
    photosLayout->addWidget(m_overlayWidget);
    photosLayout->addLayout(overlayControlsRow);
    photosLayout->addWidget(m_imageHintLabel);
    photosLayout->addLayout(imageActionsLayout);
    photosLayout->addWidget(m_thumbnailScrollArea);
    photosLayout->addWidget(pcUploadTitle);
    photosLayout->addWidget(pcUploadHintLabel);
    photosLayout->addWidget(m_pendingLocalImagesLabel);
    photosLayout->addWidget(m_pendingLocalImagesList);
    photosLayout->addLayout(pcUploadActionsLayout);
    photosLayout->addStretch();

    // ════════════════════════════════════════════════════════════════════════
    // TAB 3 — Analýza
    // ════════════════════════════════════════════════════════════════════════
    auto *analysisLayout = makeScrollPage(m_tabWidget, QString::fromUtf8("Spustit anal\u00fdzu"));

    auto *runAnalysisCard = new QFrame();
    runAnalysisCard->setObjectName("proposalInnerCard");
    auto *runAnalysisCardLayout = new QVBoxLayout(runAnalysisCard);
    runAnalysisCardLayout->setContentsMargins(16, 16, 16, 16);
    runAnalysisCardLayout->setSpacing(10);
    auto *runAnalysisHint = new QLabel(
        QString::fromUtf8("Po nahr\u00e1n\u00ed fotek spus\u0165te AI anal\u00fdzu. Server vyhodnost\u00ed typ objektu, stav povrchu, plochu a navrhne materi\u00e1ly i postup pr\u00e1ce."));
    runAnalysisHint->setObjectName("hintLabel");
    runAnalysisHint->setWordWrap(true);
    m_runAnalysisButton = new QPushButton(QString::fromUtf8("Spustit anal\u00fdzu"));
    m_runAnalysisButton->setEnabled(false);
    m_runAnalysisButton->setWhatsThis(QString::fromUtf8("Ode\u0161le fotky na server a spust\u00ed AI anal\u00fdzu. Server automaticky zjist\u00ed plochu, doporu\u010d\u00ed materi\u00e1ly a postup pr\u00e1ce."));
    m_analysisJobStatusLabel = new QLabel(QString());
    m_analysisJobStatusLabel->setObjectName("hintLabel");
    m_analysisJobStatusLabel->setWordWrap(true);
    m_analysisJobStatusLabel->hide();
    auto *runAnalysisActionsRow = new QHBoxLayout();
    runAnalysisActionsRow->addWidget(m_runAnalysisButton);
    runAnalysisActionsRow->addStretch();
    runAnalysisCardLayout->addWidget(runAnalysisHint);
    runAnalysisCardLayout->addLayout(runAnalysisActionsRow);
    runAnalysisCardLayout->addWidget(m_analysisJobStatusLabel);

    analysisLayout->addWidget(runAnalysisCard);
    analysisLayout->addStretch();

    // ════════════════════════════════════════════════════════════════════════
    // TAB 4 — Nabídka
    // ════════════════════════════════════════════════════════════════════════
    auto *offerLayout = makeScrollPage(m_tabWidget, "Nabidka");

    auto *proposalCard = new QFrame();
    proposalCard->setObjectName("summaryCard");
    auto *proposalLayout = new QVBoxLayout(proposalCard);
    proposalLayout->setContentsMargins(16, 16, 16, 16);
    proposalLayout->setSpacing(12);

    auto *proposalSummaryCard = new QFrame(proposalCard);
    proposalSummaryCard->setObjectName("proposalInnerCard");
    auto *proposalSummaryLayout = new QFormLayout(proposalSummaryCard);
    proposalSummaryLayout->setContentsMargins(12, 12, 12, 12);
    proposalSummaryLayout->setVerticalSpacing(8);
    m_proposalStatusValueLabel = new QLabel("-", proposalSummaryCard);
    m_proposalSubjectEdit = new QLineEdit(proposalSummaryCard);
    m_proposalSummaryEdit = new QPlainTextEdit(proposalSummaryCard);
    m_proposalSummaryEdit->setMaximumHeight(80);
    m_proposalMaterialCostEdit = new QLineEdit(proposalSummaryCard);
    m_proposalLaborCostEdit = new QLineEdit(proposalSummaryCard);
    m_proposalTransportCostEdit = new QLineEdit(proposalSummaryCard);
    m_proposalTransportCostEdit->setPlaceholderText("0.00");
    m_proposalAmortizationEdit = new QLineEdit(proposalSummaryCard);
    m_proposalMarginEdit = new QLineEdit(proposalSummaryCard);
    m_proposalTotalValueLabel = new QLabel("-", proposalSummaryCard);
    m_proposalSupplierEdit = new QLineEdit(proposalSummaryCard);
    m_proposalCompanyEdit = new QLineEdit(proposalSummaryCard);
    proposalSummaryLayout->addRow("Stav navrhu", m_proposalStatusValueLabel);
    proposalSummaryLayout->addRow("Predmet nabidky", m_proposalSubjectEdit);
    proposalSummaryLayout->addRow("Shrnuti", m_proposalSummaryEdit);
    proposalSummaryLayout->addRow("Cena prace (CZK)", m_proposalLaborCostEdit);
    proposalSummaryLayout->addRow("Cena materialu (CZK)", m_proposalMaterialCostEdit);
    proposalSummaryLayout->addRow("Doprava (CZK)", m_proposalTransportCostEdit);
    proposalSummaryLayout->addRow("Amortizace (CZK)", m_proposalAmortizationEdit);
    proposalSummaryLayout->addRow("Marze (%)", m_proposalMarginEdit);
    proposalSummaryLayout->addRow("Celkem vcetne DPH", m_proposalTotalValueLabel);
    proposalSummaryLayout->addRow("Navrzeny dodavatel", m_proposalSupplierEdit);
    proposalSummaryLayout->addRow("Realizacni firma", m_proposalCompanyEdit);

    auto *proposalActionsLayout = new QHBoxLayout();
    proposalActionsLayout->setSpacing(10);
    m_saveProposalButton = new QPushButton("Ulozit navrh", proposalCard);
    m_saveProposalButton->setEnabled(false);
    m_saveProposalButton->setWhatsThis(QString::fromUtf8("Ulo\u017e\u00ed rozepsan\u00fd n\u00e1vrh nab\u00eddky na server. N\u00e1vrh z\u016fstane ve stavu 'rozpracov\u00e1no' a m\u016f\u017eete ho d\u00e1le upravovat."));
    m_createFinalProposalButton = new QPushButton("Vytvorit finalni verzi", proposalCard);
    m_createFinalProposalButton->setEnabled(false);
    m_createFinalProposalButton->setWhatsThis(QString::fromUtf8("Vytvo\u0159\u00ed fin\u00e1ln\u00ed verzi nab\u00eddky. Server automaticky vygeneruje DOCX a PDF dokumenty p\u0159ipraven\u00e9 k odesl\u00e1n\u00ed z\u00e1kazn\u00edkovi."));
    proposalActionsLayout->addWidget(m_saveProposalButton);
    proposalActionsLayout->addWidget(m_createFinalProposalButton);
    proposalActionsLayout->addStretch();

    auto *proposalWorkItemsTitle = new QLabel(QString::fromUtf8("Technologick\u00fd postup"), proposalCard);
    proposalWorkItemsTitle->setObjectName("subSectionTitle");
    m_proposalWorkItemsList = new QLabel(proposalCard);
    m_proposalWorkItemsList->setObjectName("hintLabel");
    m_proposalWorkItemsList->setWordWrap(true);

    auto *proposalMaterialsTitle = new QLabel("Navrzene materialy", proposalCard);
    proposalMaterialsTitle->setObjectName("subSectionTitle");
    m_proposalMaterialsList = new QListWidget(proposalCard);
    m_proposalMaterialsList->setObjectName("detailList");
    m_proposalMaterialsList->setMaximumHeight(200);
    m_proposalMaterialsList->setEditTriggers(QAbstractItemView::NoEditTriggers);
    m_proposalMaterialsList->setFocusPolicy(Qt::NoFocus);
    m_proposalMaterialsList->setItemDelegate(new NoFocusRectDelegate(m_proposalMaterialsList));
    m_proposalMaterialsList->setToolTip(QString::fromUtf8("Dvojklikem na polo\u017eku otev\u0159ete editaci mno\u017estv\u00ed a ceny."));
    connect(m_proposalMaterialsList, &QListWidget::itemDoubleClicked, this,
        [this](QListWidgetItem *item) {
            const int row = m_proposalMaterialsList->row(item);
            if (row < 0 || row >= m_currentProposalMaterialItems.size()) return;

            auto &mat = m_currentProposalMaterialItems[row];

            QDialog dlg(this);
            dlg.setWindowTitle(QString::fromUtf8("Upravit polo\u017eku"));
            auto *layout = new QFormLayout(&dlg);
            layout->setContentsMargins(16, 16, 16, 16);
            layout->setSpacing(10);

            layout->addRow(QString::fromUtf8("N\u00e1zev:"), new QLabel(mat.name, &dlg));

            auto *qtyEdit = new QLineEdit(QString::number(mat.quantity, 'f', 2), &dlg);
            qtyEdit->setValidator(new QDoubleValidator(0, 1e9, 4, qtyEdit));
            layout->addRow(QString::fromUtf8("Mno\u017estv\u00ed:"), qtyEdit);

            auto *unitEdit = new QLineEdit(mat.unit, &dlg);
            layout->addRow("Jednotka:", unitEdit);

            auto *priceEdit = new QLineEdit(QString::number(mat.unitPrice, 'f', 2), &dlg);
            priceEdit->setValidator(new QDoubleValidator(0, 1e9, 4, priceEdit));
            layout->addRow(QString::fromUtf8("Cena/j. (CZK):"), priceEdit);

            auto *totalLabel = new QLabel(&dlg);
            layout->addRow("Celkem:", totalLabel);

            auto updateTotal = [qtyEdit, priceEdit, totalLabel]() {
                const double q = qtyEdit->text().replace(',', '.').toDouble();
                const double p = priceEdit->text().replace(',', '.').toDouble();
                totalLabel->setText(QString::fromUtf8("%1 CZK").arg(q * p, 0, 'f', 2));
            };
            updateTotal();
            connect(qtyEdit, &QLineEdit::textChanged, &dlg, [updateTotal](const QString &) { updateTotal(); });
            connect(priceEdit, &QLineEdit::textChanged, &dlg, [updateTotal](const QString &) { updateTotal(); });

            auto *buttons = new QDialogButtonBox(
                QDialogButtonBox::Ok | QDialogButtonBox::Cancel, &dlg);
            layout->addRow(buttons);
            connect(buttons, &QDialogButtonBox::accepted, &dlg, &QDialog::accept);
            connect(buttons, &QDialogButtonBox::rejected, &dlg, &QDialog::reject);

            if (dlg.exec() != QDialog::Accepted) return;

            const double newQty   = qtyEdit->text().replace(',', '.').toDouble();
            const double newPrice = priceEdit->text().replace(',', '.').toDouble();
            mat.quantity  = newQty;
            mat.unit      = unitEdit->text().trimmed();
            mat.unitPrice = newPrice;
            mat.totalPrice = newQty * newPrice;

            item->setText(formatMaterialItem(mat));

            // Přepočítej celkové náklady na materiál
            double total = 0.0;
            for (const auto &m : m_currentProposalMaterialItems) total += m.totalPrice;
            if (m_proposalMaterialCostEdit)
                m_proposalMaterialCostEdit->setText(QString::number(total, 'f', 2));

            m_isDirty = true;
        });

    auto *finalProposalTitle = new QLabel("Finalni verze nabidky", proposalCard);
    finalProposalTitle->setObjectName("subSectionTitle");
    auto *finalProposalCard = new QFrame(proposalCard);
    finalProposalCard->setObjectName("proposalInnerCard");
    finalProposalCard->setMinimumHeight(120);
    auto *finalProposalLayout = new QFormLayout(finalProposalCard);
    finalProposalLayout->setContentsMargins(12, 12, 12, 12);
    finalProposalLayout->setVerticalSpacing(10);
    m_finalProposalStatusValueLabel = new QLabel("zatim nevytvoreno", finalProposalCard);
    m_finalProposalVersionValueLabel = new QLabel("-", finalProposalCard);
    m_finalProposalSubjectValueLabel = new QLabel("-", finalProposalCard);
    m_finalProposalSubjectValueLabel->setWordWrap(true);
    m_finalProposalSummaryValueLabel = new QLabel(
        "Po potvrzeni server pripravi DOCX i PDF automaticky.", finalProposalCard);
    m_finalProposalSummaryValueLabel->setWordWrap(true);
    m_finalProposalSummaryValueLabel->setAlignment(Qt::AlignLeft | Qt::AlignTop);
    m_finalProposalSummaryValueLabel->setMinimumHeight(42);
    m_finalProposalTotalValueLabel = new QLabel("-", finalProposalCard);
    finalProposalLayout->addRow("Stav", m_finalProposalStatusValueLabel);
    finalProposalLayout->addRow("Zdroj", m_finalProposalVersionValueLabel);
    finalProposalLayout->addRow("Predmet", m_finalProposalSubjectValueLabel);
    finalProposalLayout->addRow("Shrnuti", m_finalProposalSummaryValueLabel);
    finalProposalLayout->addRow("Celkem", m_finalProposalTotalValueLabel);

    proposalLayout->addWidget(proposalSummaryCard);
    proposalLayout->addLayout(proposalActionsLayout);
    proposalLayout->addWidget(proposalWorkItemsTitle);
    proposalLayout->addWidget(m_proposalWorkItemsList);
    proposalLayout->addWidget(proposalMaterialsTitle);
    proposalLayout->addWidget(m_proposalMaterialsList);
    proposalLayout->addWidget(finalProposalTitle);
    proposalLayout->addWidget(finalProposalCard);

    offerLayout->addWidget(proposalCard);
    offerLayout->addStretch();

    // ════════════════════════════════════════════════════════════════════════
    // TAB 5 — Výstup zakázky
    // ════════════════════════════════════════════════════════════════════════
    auto *sendLayout = makeScrollPage(m_tabWidget, QString::fromUtf8("V\u00fdstup zak\u00e1zky"));

    auto *sendCard = new QFrame();
    sendCard->setObjectName("summaryCard");
    auto *sendCardLayout = new QVBoxLayout(sendCard);
    sendCardLayout->setContentsMargins(16, 16, 16, 16);
    sendCardLayout->setSpacing(12);

    // Export section
    auto *exportTitle = new QLabel("Exporty", sendCard);
    exportTitle->setObjectName("subSectionTitle");
    auto *exportActionsLayout = new QHBoxLayout();
    exportActionsLayout->setSpacing(10);
    m_downloadDraftDocxButton = new QPushButton(QString::fromUtf8("N\u00e1vrh (DOCX)"), sendCard);
    m_downloadDraftDocxButton->setEnabled(false);
    m_downloadDraftDocxButton->setWhatsThis(QString::fromUtf8("St\u00e1hne pracovn\u00ed verzi nab\u00eddky ve form\u00e1tu Word (DOCX). Vhodn\u00e9 pro dal\u0161\u00ed \u00fapravy p\u0159ed odesl\u00e1n\u00edm."));
    m_downloadQuoteDocxButton = new QPushButton(QString::fromUtf8("Nab\u00eddka (DOCX)"), sendCard);
    m_downloadQuoteDocxButton->setEnabled(false);
    m_downloadQuoteDocxButton->setWhatsThis(QString::fromUtf8("St\u00e1hne fin\u00e1ln\u00ed nab\u00eddku ve form\u00e1tu Word (DOCX). Dostupn\u00e9 po vytvo\u0159en\u00ed fin\u00e1ln\u00ed verze."));
    m_downloadQuotePdfButton = new QPushButton(QString::fromUtf8("Nab\u00eddka (PDF)"), sendCard);
    m_downloadQuotePdfButton->setEnabled(false);
    m_downloadQuotePdfButton->setWhatsThis(QString::fromUtf8("St\u00e1hne fin\u00e1ln\u00ed nab\u00eddku ve form\u00e1tu PDF. Tento soubor je ur\u010den p\u0159\u00edmo pro z\u00e1kazn\u00edka."));
    m_exportZipButton = new QPushButton(QString::fromUtf8("Exportovat jako ZIP"), sendCard);
    m_exportZipButton->setObjectName("exportZipButton");
    m_exportZipButton->setEnabled(false);
    m_exportZipButton->setWhatsThis(QString::fromUtf8("Ulo\u017e\u00ed cel\u00e9 podklady zak\u00e1zky do ZIP archivu: fin\u00e1ln\u00ed nab\u00eddka (DOCX), fotky a datov\u00fd soubor JSON."));
    exportActionsLayout->addWidget(m_downloadDraftDocxButton);
    exportActionsLayout->addWidget(m_downloadQuoteDocxButton);
    exportActionsLayout->addWidget(m_downloadQuotePdfButton);
    exportActionsLayout->addStretch();

    connect(m_downloadDraftDocxButton, &QPushButton::clicked, this, [this]() {
        downloadExport("proposal-docx");
    });
    connect(m_downloadQuoteDocxButton, &QPushButton::clicked, this, [this]() {
        downloadExport("quote-docx");
    });
    connect(m_downloadQuotePdfButton, &QPushButton::clicked, this, [this]() {
        downloadExport("quote-pdf");
    });
    connect(m_exportZipButton, &QPushButton::clicked, this, &CaseDetailView::exportAsZip);

    // Separator line
    auto *separator = new QFrame(sendCard);
    separator->setFrameShape(QFrame::HLine);
    separator->setObjectName("hintLabel");

    // Send section
    auto *sendHint = new QLabel(
        QString::fromUtf8("Po vytvo\u0159en\u00ed fin\u00e1ln\u00ed verze ode\u0161lete nab\u00eddku z\u00e1kazn\u00edkovi. Z\u00e1kazn\u00edk obdr\u017e\u00ed PDF na sv\u016fj email."),
        sendCard);
    sendHint->setObjectName("hintLabel");
    sendHint->setWordWrap(true);
    m_sendCaseButton = new QPushButton(QString::fromUtf8("Odeslat z\u00e1kazn\u00edkovi"), sendCard);
    m_sendCaseButton->setEnabled(false);
    m_sendCaseButton->setWhatsThis(QString::fromUtf8("Ode\u0161le fin\u00e1ln\u00ed nab\u00eddku z\u00e1kazn\u00edkovi emailem. Z\u00e1kazn\u00edk obdr\u017e\u00ed PDF p\u0159\u00edlohu. Akce je nevratn\u00e1."));
    auto *sendActionsRow = new QHBoxLayout();
    sendActionsRow->addWidget(m_sendCaseButton);
    sendActionsRow->addStretch();

    auto *zipActionsRow = new QHBoxLayout();
    zipActionsRow->addWidget(m_exportZipButton);
    zipActionsRow->addStretch();

    sendCardLayout->addWidget(exportTitle);
    sendCardLayout->addLayout(exportActionsLayout);
    sendCardLayout->addLayout(zipActionsRow);
    sendCardLayout->addWidget(separator);
    sendCardLayout->addWidget(sendHint);
    sendCardLayout->addLayout(sendActionsRow);

    sendLayout->addWidget(sendCard);
    sendLayout->addStretch();

    rootLayout->addWidget(card);

    setStyleSheet(R"(
        QFrame#detailCard {
            background: #fffaf2;
            border: 1px solid #eadcc8;
            border-radius: 18px;
        }
        QTabWidget#detailTabs::pane {
            border: 1px solid #eadcc8;
            border-radius: 12px;
            background: #fffaf2;
        }
        QTabWidget#detailTabs > QTabBar::tab {
            background: #f0e4d0;
            border: 1px solid #e0cdb8;
            border-bottom: none;
            border-radius: 8px 8px 0 0;
            padding: 8px 18px;
            font-weight: 600;
            color: #5a4a38;
            min-width: 80px;
        }
        QTabWidget#detailTabs > QTabBar::tab:selected {
            background: #fffaf2;
            color: #b46d35;
            border-bottom: 1px solid #fffaf2;
        }
        QTabWidget#detailTabs > QTabBar::tab:hover:!selected {
            background: #ede0cc;
        }
        QWidget#tabPage {
            background: #fffaf2;
        }
        QFrame#variantCard {
            background: #f7efe4;
            border: 1px solid #eadcc8;
            border-radius: 12px;
            min-height: 80px;
        }
        QLabel#variantTitle {
            font-weight: 700;
            font-size: 14px;
            color: #5a4a38;
        }
        QLabel#variantTotal {
            font-weight: 700;
            font-size: 18px;
            color: #b46d35;
        }
        QLabel#eyebrowLabel {
            color: #b46d35;
            font-weight: 700;
            letter-spacing: 1px;
            font-size: 12px;
        }
        QLabel#sectionTitle {
            font-size: 24px;
            font-weight: 700;
            color: #1f2933;
        }
        QLabel#subSectionTitle {
            font-size: 18px;
            font-weight: 700;
            color: #1f2933;
        }
        QLabel#hintLabel {
            color: #607080;
        }
        QLabel#errorLabel {
            color: #a3341d;
            font-weight: 600;
        }
        QLabel#primaryImageLabel {
            color: #1f2933;
            font-weight: 600;
            font-size: 16px;
        }
        QPushButton#overlayModeBtn {
            border: 1px solid #d4b896;
            border-radius: 6px;
            padding: 5px 14px;
            background: #f0e4d0;
            color: #5a4a38;
            font-weight: 600;
        }
        QPushButton#overlayModeBtn:checked {
            background: #d18841;
            color: white;
            border-color: #b46d35;
        }
        QPushButton#overlayModeBtn:hover:!checked {
            background: #e8d8c0;
        }
        QPushButton#imageNavButton {
            min-width: 40px;
            max-width: 40px;
            min-height: 40px;
            max-height: 40px;
            border-radius: 20px;
            font-size: 26px;
            font-weight: 700;
            color: #111111;
            text-align: center;
            padding: 0;
        }
        QFrame#summaryCard {
            background: #f7efe4;
            border: 1px solid #eadcc8;
            border-radius: 14px;
        }
        QFrame#proposalInnerCard {
            background: #fffaf2;
            border: 1px solid #eadcc8;
            border-radius: 12px;
        }
        QListWidget#detailList {
            background: #f7efe4;
            border: 1px solid #eadcc8;
            border-radius: 14px;
            padding: 8px;
        }
        QListWidget#detailList::item {
            padding: 10px;
            margin: 4px 0;
            border-radius: 10px;
            background: #fffaf2;
        }
        QListWidget#detailList::item:selected {
            background: #f0d8bb;
            color: #1f2933;
            border: none;
            outline: none;
        }
        QListWidget#detailList::item:focus {
            color: #1f2933;
            border: none;
            outline: none;
        }
        QScrollArea#thumbnailScrollArea {
            background: #f7efe4;
            border: 1px solid #eadcc8;
            border-radius: 14px;
        }
        QWidget#thumbnailStripWidget {
            background: #f7efe4;
        }
        QPushButton#thumbnailButton {
            min-width: 132px;
            max-width: 132px;
            min-height: 102px;
            max-height: 102px;
            border-radius: 12px;
            background: #fffaf2;
            border: 1px solid #eadcc8;
            padding: 6px;
        }
        QPushButton#thumbnailButton[selected="true"] {
            border: 2px solid #d18841;
        }
        QScrollArea#thumbnailScrollArea QScrollBar:horizontal {
            height: 12px;
            background: #efe4d2;
            border-radius: 6px;
            margin: 6px 12px 0 12px;
        }
        QScrollArea#thumbnailScrollArea QScrollBar::handle:horizontal {
            background: #cfa980;
            min-width: 30px;
            border-radius: 6px;
        }
        QScrollArea#thumbnailScrollArea QScrollBar::add-line:horizontal,
        QScrollArea#thumbnailScrollArea QScrollBar::sub-line:horizontal {
            width: 0;
            border: none;
            background: transparent;
        }
        QLabel#readOnlyBanner {
            background: #fef3cd;
            color: #856404;
            border: 1px solid #ffc107;
            border-radius: 8px;
            padding: 8px 12px;
            font-weight: 600;
        }
        QPushButton#editUnlockButton {
            background: #d18841;
            border: 1px solid #b46d35;
            border-radius: 8px;
            color: #fff9f2;
            font-weight: 700;
            padding: 8px 20px;
        }
        QPushButton#editUnlockButton:hover {
            background: #c97b3d;
        }
        QLabel#dashPhoto {
            background: #f0e4d0;
            border: 1px solid #eadcc8;
            border-radius: 14px;
            color: #9a8878;
            font-size: 14px;
        }
        QLabel#dashTotalKey {
            font-weight: 700;
            font-size: 14px;
            color: #1f2933;
        }
        QLabel#dashTotal {
            font-weight: 700;
            font-size: 18px;
            color: #b46d35;
        }
        QListWidget#workflowList {
            background: #f7efe4;
            border: 1px solid #eadcc8;
            border-radius: 10px;
            padding: 6px;
        }
        QListWidget#workflowList::item {
            padding: 8px 10px;
            margin: 2px 0;
            border-radius: 8px;
            background: #fffaf2;
            color: #1f2933;
        }
    )");

    connect(m_moveUpButton, &QPushButton::clicked, this, [this]() {
        selectAdjacentImage(-1);
    });
    connect(m_moveDownButton, &QPushButton::clicked, this, [this]() {
        selectAdjacentImage(1);
    });
    connect(m_setPrimaryButton, &QPushButton::clicked, this, [this]() {
        setSelectedImageAsPrimary();
    });
    connect(m_setAnalysisReferenceButton, &QPushButton::clicked, this, [this]() {
        setSelectedImageAsAnalysisReference();
    });
    if (m_saveAsButton) connect(m_saveAsButton, &QPushButton::clicked, this, [this]() {
        duplicateCase("copy");
    });
    if (m_newVariantButton) connect(m_newVariantButton, &QPushButton::clicked, this, [this]() {
        if (!m_caseId.isEmpty()) {
            emit newVariantRequested(m_caseId);
        }
    });
    connect(m_sendCaseButton, &QPushButton::clicked, this, [this]() {
        sendCurrentCase();
    });
    // Overlay mode toggles
    auto setOverlayMode = [this](ImageOverlayWidget::Mode mode) {
        m_overlayWidget->setMode(mode);
        m_overlayModeViewButton->setChecked(mode == ImageOverlayWidget::Mode::View);
        m_overlayModeRectButton->setChecked(mode == ImageOverlayWidget::Mode::Rectangle);
        m_overlayModePolyButton->setChecked(mode == ImageOverlayWidget::Mode::Polygon);
    };
    connect(m_overlayModeViewButton, &QPushButton::clicked, this, [setOverlayMode]() {
        setOverlayMode(ImageOverlayWidget::Mode::View);
    });
    connect(m_overlayModeRectButton, &QPushButton::clicked, this, [setOverlayMode]() {
        setOverlayMode(ImageOverlayWidget::Mode::Rectangle);
    });
    connect(m_overlayModePolyButton, &QPushButton::clicked, this, [setOverlayMode]() {
        setOverlayMode(ImageOverlayWidget::Mode::Polygon);
    });
    connect(m_overlayWidget, &ImageOverlayWidget::selectionChanged, this, [this]() {
        if (m_overlayConfirmButton) {
            m_overlayConfirmButton->setEnabled(m_overlayWidget->hasSelection());
        }
    });
    connect(m_overlayConfirmButton, &QPushButton::clicked, this, [this]() {
        confirmSelectionArea();
    });
    connect(m_runAnalysisButton, &QPushButton::clicked, this, [this]() {
        triggerAnalysis();
    });
    m_analysisPollingTimer = new QTimer(this);
    m_analysisPollingTimer->setInterval(2000);
    connect(m_analysisPollingTimer, &QTimer::timeout, this, [this]() {
        pollAnalysisStatus();
    });
    connect(m_saveProposalButton, &QPushButton::clicked, this, [this]() {
        saveProposalDraft();
    });
    connect(m_createFinalProposalButton, &QPushButton::clicked, this, [this]() {
        createFinalProposal();
    });
    connect(m_dashRunAnalysisButton, &QPushButton::clicked, this, [this]() {
        triggerAnalysis();
    });
    connect(m_addImagesButton, &QPushButton::clicked, this, [this]() {
        selectLocalImages();
    });
    connect(m_convertImagesButton, &QPushButton::clicked, this, [this]() {
        convertPendingLocalImages();
    });
    m_imagePollingTimer = new QTimer(this);
    m_imagePollingTimer->setInterval(kImagePollingIntervalMs);
    connect(m_imagePollingTimer, &QTimer::timeout, this, [this]() {
        pollImageStatuses();
    });

    // ── Dirty tracking (set up once; applyCaseData resets m_isDirty after) ──
    const auto markDirty = [this]() { m_isDirty = true; };
    connect(m_proposalSubjectEdit, &QLineEdit::textEdited, this, markDirty);
    connect(m_proposalSummaryEdit, &QPlainTextEdit::textChanged, this, markDirty);
    connect(m_proposalMaterialCostEdit, &QLineEdit::textEdited, this, markDirty);
    connect(m_proposalLaborCostEdit, &QLineEdit::textEdited, this, markDirty);
    connect(m_proposalTransportCostEdit, &QLineEdit::textEdited, this, markDirty);
    connect(m_proposalAmortizationEdit, &QLineEdit::textEdited, this, markDirty);
    connect(m_proposalMarginEdit, &QLineEdit::textEdited, this, markDirty);
    connect(m_proposalSupplierEdit, &QLineEdit::textEdited, this, markDirty);
    connect(m_proposalCompanyEdit, &QLineEdit::textEdited, this, markDirty);

    updatePendingLocalImagesPanel();
}

void CaseDetailView::setCase(const QString &caseId)
{
    if (caseId.isEmpty()) {
        clearCase();
        return;
    }

    if (!m_caseId.isEmpty() && m_caseId != caseId) {
        stopImageStatusPolling();
        m_selectedImageId.clear();
        m_pendingLocalImagePaths.clear();
        m_preparedLocalImages.clear();
        updatePendingLocalImagesPanel();
    }

    m_caseId = caseId;
    ApiService apiService;
    CaseDetailViewModel viewModel;
    const auto caseDto = viewModel.loadCase(caseId, apiService);

    if (ApiService::sessionExpired()) {
        emit sessionExpired();
        return;
    }

    if (caseDto.id.isEmpty() && !viewModel.errorMessage().isEmpty()) {
        m_errorLabel->setText(viewModel.errorMessage());
        m_errorLabel->show();
        return;
    }

    m_errorLabel->hide();
    applyCaseData(caseDto);

    QString imageErrorMessage;
    if (!refreshImagesFromBackend(&imageErrorMessage)) {
        setImageHintMessage(imageErrorMessage, true);
        return;
    }

    updateImagesPanel();

    if (m_images.empty()) {
        setImageHintMessage("Case zatim nema zadne obrazky.");
    } else {
        setImageHintMessage(
            QString("Nacteno %1 obrazku z backendu. Stav: %2.")
                .arg(m_images.size())
                .arg(summarizeServerImageStatuses(m_images)));
    }
}

void CaseDetailView::applyCaseData(const CaseDto &caseDto)
{
    m_currentCase = caseDto;
    m_isReferenceDataset = caseDto.isReferenceDataset;
    m_source = caseDto.source.isEmpty() ? QStringLiteral("mobile") : caseDto.source;
    const bool isDesktopCase = (m_source == QStringLiteral("desktop"));
    if (m_tabWidget) {
        m_tabWidget->setTabVisible(2, isDesktopCase); // Analýza tab only for PC cases
    }
    if (m_dashRunAnalysisButton) {
        m_dashRunAnalysisButton->setVisible(isDesktopCase);
    }
    m_expectedScope = caseDto.expectedScope;
    m_currentRepairScope = caseDto.repairScope;
    m_currentProposalWorkItems = caseDto.proposalWorkItems;
    m_currentProposalMaterials = caseDto.proposalMaterials;
    m_currentProposalMaterialItems = caseDto.proposalMaterialItems;
    m_expectedPrimaryFilename = caseDto.expectedPrimaryFilename;
    m_expectedAnalysisReferenceFilename = caseDto.expectedAnalysisReferenceFilename;
    m_referenceSourcePage = caseDto.referenceSourcePage;

    m_titleLabel->setText(caseDto.title.isEmpty() ? "Case detail" : caseDto.title);
    m_subtitleLabel->setText(
        caseDto.description.isEmpty()
            ? "Server pripravi navrh, tady ho zkontrolujes, upravis a potvrdis do finalni verze."
            : caseDto.description);
    m_statusValueLabel->setText(caseDto.status.isEmpty() ? "-" : caseDto.status);
    m_addressValueLabel->setText(caseDto.addressLabel.isEmpty() ? "-" : caseDto.addressLabel);
    m_scopeValueLabel->setText(caseDto.repairScope.isEmpty() ? "-" : localizeRepairScope(caseDto.repairScope));
    m_areaValueLabel->setText(caseDto.areaLabel.isEmpty() ? "-" : caseDto.areaLabel);

    // ── Dashboard widgets ─────────────────────────────────────────────────
    if (m_dashObjTypeLabel) m_dashObjTypeLabel->setText(
        caseDto.analysisObjectType.isEmpty() ? "-" : localizeObjectType(caseDto.analysisObjectType));
    if (m_dashAreaLabel) {
        if (caseDto.hasAnalysis && caseDto.analysisEstimatedAreaSqm > 0.0) {
            const int pct = static_cast<int>(caseDto.analysisAreaConfidence * 100.0 + 0.5);
            m_dashAreaLabel->setText(
                QString("%1 m\u00B2  (spolehlivost %2 %)")
                    .arg(caseDto.analysisEstimatedAreaSqm, 0, 'f', 1).arg(pct));
        } else { m_dashAreaLabel->setText("-"); }
    }
    if (m_dashSurfaceLabel) m_dashSurfaceLabel->setText(
        caseDto.analysisSurfaceCondition.isEmpty() ? "-" : localizeSurfaceCondition(caseDto.analysisSurfaceCondition));
    if (m_dashScopeLabel) m_dashScopeLabel->setText(
        caseDto.analysisRecommendedScope.isEmpty() ? "-" : localizeRecommendedScope(caseDto.analysisRecommendedScope));
    if (m_dashDurationLabel) {
        if (caseDto.hasAnalysis && (caseDto.analysisDurationDays > 0.0 || caseDto.analysisLaborHours > 0.0)) {
            m_dashDurationLabel->setText(
                QString("%1 dn\u00ED  |  %2 h pr\u00E1ce")
                    .arg(caseDto.analysisDurationDays, 0, 'f', 1)
                    .arg(caseDto.analysisLaborHours, 0, 'f', 1));
        } else { m_dashDurationLabel->setText("-"); }
    }
    if (m_dashLaborLabel) m_dashLaborLabel->setText(
        caseDto.proposalLaborCostLabel.isEmpty() ? "-" : caseDto.proposalLaborCostLabel);
    if (m_dashMaterialLabel) m_dashMaterialLabel->setText(
        caseDto.proposalMaterialCostLabel.isEmpty() ? "-" : caseDto.proposalMaterialCostLabel);
    if (m_dashTransportLabel) m_dashTransportLabel->setText(
        caseDto.proposalTransportCostLabel.isEmpty() ? "-" : caseDto.proposalTransportCostLabel);
    if (m_dashMarginLabel) m_dashMarginLabel->setText(
        caseDto.proposalMarginLabel.isEmpty() ? "-" : caseDto.proposalMarginLabel);
    if (m_dashTotalLabel) m_dashTotalLabel->setText(
        caseDto.proposalTotalPriceLabel.isEmpty() ? "-" : caseDto.proposalTotalPriceLabel);
    if (m_dashWorkflowList) {
        m_dashWorkflowList->clear();
        if (caseDto.analysisWorkflowSteps.isEmpty()) {
            m_dashWorkflowList->addItem(
                QString::fromUtf8("Postup pr\u00e1ce bude k dispozici po dokon\u010den\u00ed anal\u00fdzy."));
        } else {
            m_dashWorkflowList->addItems(caseDto.analysisWorkflowSteps);
        }
    }
    const auto draftStatus = caseDto.workflowDraftStatus.isEmpty()
        ? caseDto.proposalStatus
        : caseDto.workflowDraftStatus;
    const auto finalProposalStatus = caseDto.workflowFinalProposalStatus.isEmpty()
        ? caseDto.finalProposalStatus
        : caseDto.workflowFinalProposalStatus;

    m_proposalStatusValueLabel->setText(draftWorkflowStatusLabel(draftStatus));
    m_workflowStatusValueLabel->setText(workflowSummaryLabel(caseDto));
    m_workflowBlockingReasonsValueLabel->setText(workflowBlockingReasonsLabel(caseDto.workflowBlockingReasons));
    updateReferenceTestContextLabel();
    m_proposalSubjectEdit->setText(caseDto.proposalSubject);
    m_proposalSummaryEdit->setPlainText(caseDto.proposalSummary);
    m_proposalLaborCostEdit->setText(formatDecimalForEdit(caseDto.proposalLaborCostLabel));
    m_proposalMaterialCostEdit->setText(formatDecimalForEdit(caseDto.proposalMaterialCostLabel));
    if (m_proposalTransportCostEdit) {
        m_proposalTransportCostEdit->setText(formatDecimalForEdit(caseDto.proposalTransportCostLabel));
    }
    m_proposalAmortizationEdit->setText(formatDecimalForEdit(caseDto.proposalAmortizationLabel));
    m_proposalMarginEdit->setText(formatDecimalForEdit(caseDto.proposalMarginLabel));
    m_proposalTotalValueLabel->setText(caseDto.proposalTotalPriceLabel.isEmpty() ? "-" : caseDto.proposalTotalPriceLabel);
    m_proposalSupplierEdit->setText(caseDto.proposalRecommendedSupplier);
    m_proposalCompanyEdit->setText(caseDto.proposalRecommendedCompany);
    m_finalProposalStatusValueLabel->setText(finalProposalStatusLabel(finalProposalStatus));
    m_finalProposalVersionValueLabel->setText(caseDto.finalProposalDraftVersionLabel.isEmpty() ? "-" : caseDto.finalProposalDraftVersionLabel);
    m_finalProposalSubjectValueLabel->setText(caseDto.finalProposalSubject.isEmpty() ? "-" : caseDto.finalProposalSubject);
    m_finalProposalSummaryValueLabel->setText(
        caseDto.finalProposalSummary.isEmpty()
            ? "Zatim neni vytvorena finalni verze. Po potvrzeni server pripravi DOCX i PDF automaticky."
            : caseDto.finalProposalSummary);
    m_finalProposalTotalValueLabel->setText(
        caseDto.finalProposalTotalPriceLabel.isEmpty() ? "-" : caseDto.finalProposalTotalPriceLabel);
    m_proposalWorkItemsList->setText(
        caseDto.proposalWorkItems.isEmpty()
            ? QString::fromUtf8("N\u00e1vrh praci se dopln\u00ed po zpracov\u00e1n\u00ed fotek.")
            : caseDto.proposalWorkItems.join(QString::fromUtf8(" \u2022 ")));
    m_proposalMaterialsList->clear();
    if (m_currentProposalMaterialItems.isEmpty()) {
        m_proposalMaterialsList->addItem(
            QString::fromUtf8("N\u00e1vrh materi\u00e1lu se dopln\u00ed po zpracov\u00e1n\u00ed fotek."));
    } else {
        for (const auto &mat : m_currentProposalMaterialItems) {
            m_proposalMaterialsList->addItem(formatMaterialItem(mat));
        }
    }

    m_analysisId = caseDto.analysisId;
    if (m_overlayWidget) {
        m_overlayWidget->setAiPolygon(caseDto.analysisMaskPolygon);
    }

    // Analysis / Findings
    if (m_analysisObjectTypeLabel) {
        m_analysisObjectTypeLabel->setText(
            caseDto.analysisObjectType.isEmpty() ? "-" : localizeObjectType(caseDto.analysisObjectType));
    }
    if (m_analysisAreaLabel) {
        if (caseDto.hasAnalysis && caseDto.analysisEstimatedAreaSqm > 0.0) {
            const int pct = static_cast<int>(caseDto.analysisAreaConfidence * 100.0 + 0.5);
            m_analysisAreaLabel->setText(
                QString("%1 m\u00B2  (spolehlivost %2 %)").arg(caseDto.analysisEstimatedAreaSqm, 0, 'f', 1).arg(pct));
        } else {
            m_analysisAreaLabel->setText("-");
        }
    }
    if (m_analysisSurfaceConditionLabel) {
        m_analysisSurfaceConditionLabel->setText(
            caseDto.analysisSurfaceCondition.isEmpty() ? "-" : localizeSurfaceCondition(caseDto.analysisSurfaceCondition));
    }
    if (m_analysisRecommendedScopeLabel) {
        m_analysisRecommendedScopeLabel->setText(
            caseDto.analysisRecommendedScope.isEmpty() ? "-" : localizeRecommendedScope(caseDto.analysisRecommendedScope));
    }
    if (m_analysisDurationLabel) {
        if (caseDto.hasAnalysis && (caseDto.analysisDurationDays > 0.0 || caseDto.analysisLaborHours > 0.0)) {
            m_analysisDurationLabel->setText(
                QString("%1 dn\xED  |  %2 h prace")
                    .arg(caseDto.analysisDurationDays, 0, 'f', 1)
                    .arg(caseDto.analysisLaborHours, 0, 'f', 1));
        } else {
            m_analysisDurationLabel->setText("-");
        }
    }
    if (m_analysisWorkflowList) {
        m_analysisWorkflowList->clear();
        if (caseDto.analysisWorkflowSteps.isEmpty()) {
            m_analysisWorkflowList->addItem("Postup prace bude k dispozici po dokonceni analyzy.");
        } else {
            m_analysisWorkflowList->addItems(caseDto.analysisWorkflowSteps);
        }
    }
    if (m_analysisMaterialsList) {
        m_analysisMaterialsList->clear();
        if (caseDto.analysisMaterialItems.isEmpty()) {
            m_analysisMaterialsList->addItem("Materialy budou k dispozici po dokonceni analyzy.");
        } else {
            m_analysisMaterialsList->addItems(caseDto.analysisMaterialItems);
        }
    }
    if (m_quoteEconomyValueLabel) {
        m_quoteEconomyValueLabel->setText(caseDto.hasQuoteVariants
            ? (caseDto.quoteEconomyLabel.isEmpty() ? "-" : caseDto.quoteEconomyLabel)
            : "Varianta bude vypoctena po analyze.");
    }
    if (m_quoteStandardValueLabel) {
        m_quoteStandardValueLabel->setText(caseDto.hasQuoteVariants
            ? (caseDto.quoteStandardLabel.isEmpty() ? "-" : caseDto.quoteStandardLabel)
            : "Varianta bude vypoctena po analyze.");
    }
    if (m_quotePremiumValueLabel) {
        m_quotePremiumValueLabel->setText(caseDto.hasQuoteVariants
            ? (caseDto.quotePremiumLabel.isEmpty() ? "-" : caseDto.quotePremiumLabel)
            : "Varianta bude vypoctena po analyze.");
    }

    if (m_runAnalysisButton) {
        m_runAnalysisButton->setEnabled(!caseDto.id.isEmpty());
    }
    if (m_saveProposalButton) {
        m_saveProposalButton->setEnabled(!caseDto.id.isEmpty());
    }
    if (m_createFinalProposalButton) {
        m_createFinalProposalButton->setEnabled(!caseDto.id.isEmpty() && caseDto.workflowCanCreateFinalProposal);
        m_createFinalProposalButton->setToolTip(caseDto.workflowCanCreateFinalProposal
            ? "Workflow je pripraveny pro vytvoreni finalni verze."
            : workflowBlockingReasonsLabel(caseDto.workflowBlockingReasons));
    }
    if (m_downloadDraftDocxButton) {
        m_downloadDraftDocxButton->setEnabled(
            !caseDto.id.isEmpty() && !caseDto.proposalStatus.isEmpty());
    }
    if (m_downloadQuoteDocxButton) {
        m_downloadQuoteDocxButton->setEnabled(
            !caseDto.id.isEmpty() && !caseDto.finalProposalStatus.isEmpty());
    }
    if (m_downloadQuotePdfButton) {
        m_downloadQuotePdfButton->setEnabled(
            !caseDto.id.isEmpty() && !caseDto.finalProposalStatus.isEmpty());
    }
    if (m_exportZipButton) {
        m_exportZipButton->setEnabled(!caseDto.id.isEmpty());
    }
    if (m_saveAsButton) {
        m_saveAsButton->setEnabled(true);
    }
    if (m_newVariantButton) {
        m_newVariantButton->setEnabled(true);
    }
    if (m_sendCaseButton) {
        const bool caseClosed = caseDto.status.compare("sent", Qt::CaseInsensitive) == 0
            || caseDto.status.compare("completed", Qt::CaseInsensitive) == 0;
        m_sendCaseButton->setEnabled(!caseDto.id.isEmpty() && !caseClosed && caseDto.workflowCanSend);
        m_sendCaseButton->setToolTip(caseDto.workflowCanSend
            ? "Finalni verze existuje, zakazku lze odeslat."
            : workflowBlockingReasonsLabel(caseDto.workflowBlockingReasons));
        const bool dashCaseClosed = caseClosed;
        if (m_dashRunAnalysisButton) m_dashRunAnalysisButton->setEnabled(!caseDto.id.isEmpty());
    }

    m_isDirty = false;
}

bool CaseDetailView::hasUnsavedChanges() const
{
    return m_isDirty;
}

QString CaseDetailView::caseSource() const
{
    return m_source;
}

void CaseDetailView::setReadOnly(bool readOnly)
{
    m_isReadOnly = readOnly;
    if (m_readOnlyBanner) m_readOnlyBanner->setVisible(readOnly);
    if (m_editUnlockButton) m_editUnlockButton->setVisible(readOnly);

    const auto edits = findChildren<QLineEdit *>();
    for (auto *e : edits) e->setReadOnly(readOnly);
    const auto textEdits = findChildren<QPlainTextEdit *>();
    for (auto *t : textEdits) t->setReadOnly(readOnly);

    const QList<QPushButton *> actionButtons = {
        m_runAnalysisButton, m_overlayModeRectButton, m_overlayModePolyButton,
        m_overlayConfirmButton, m_setPrimaryButton, m_setAnalysisReferenceButton,
        m_moveUpButton, m_moveDownButton, m_addImagesButton, m_convertImagesButton,
        m_saveProposalButton, m_createFinalProposalButton,
        m_sendCaseButton,
    };
    for (auto *btn : actionButtons) {
        if (btn) btn->setEnabled(!readOnly);
    }
}

void CaseDetailView::switchToPhotosTab()
{
    if (m_tabWidget) {
        m_tabWidget->setCurrentIndex(1);
    }
}

void CaseDetailView::triggerSave()
{
    saveProposalDraft();
}

void CaseDetailView::navigateToField(const QString &fieldKey)
{
    if (!m_tabWidget) return;

    // Nabídka tab is always at index 3
    m_tabWidget->setCurrentIndex(3);

    QWidget *targetWidget = nullptr;
    if      (fieldKey == QLatin1String("subject"))            targetWidget = m_proposalSubjectEdit;
    else if (fieldKey == QLatin1String("material_cost"))      targetWidget = m_proposalMaterialCostEdit;
    else if (fieldKey == QLatin1String("labor_cost"))         targetWidget = m_proposalLaborCostEdit;
    else if (fieldKey == QLatin1String("materials"))          targetWidget = m_proposalMaterialsList;
    else if (fieldKey == QLatin1String("amortization"))       targetWidget = m_proposalAmortizationEdit;
    else if (fieldKey == QLatin1String("margin"))             targetWidget = m_proposalMarginEdit;
    else if (fieldKey == QLatin1String("material_suppliers")) targetWidget = m_proposalSupplierEdit;

    if (!targetWidget) return;

    // Scroll to the widget within the tab's QScrollArea
    if (auto *scrollArea = qobject_cast<QScrollArea *>(m_tabWidget->widget(3))) {
        scrollArea->ensureWidgetVisible(targetWidget);
    }

    targetWidget->setFocus();
    if (auto *edit = qobject_cast<QLineEdit *>(targetWidget)) {
        edit->selectAll();
    }
}

void CaseDetailView::clearCase()
{
    stopImageStatusPolling();
    stopAnalysisPolling();
    setReadOnly(false);
    m_isDirty = false;
    m_source.clear();
    m_caseId.clear();
    if (m_tabWidget) m_tabWidget->setTabVisible(2, true);
    if (m_dashRunAnalysisButton) m_dashRunAnalysisButton->setVisible(true);
    m_analysisId.clear();
    m_selectedImageId.clear();
    m_images.clear();
    m_isReferenceDataset = false;
    m_expectedScope.clear();
    m_currentRepairScope.clear();
    m_currentProposalWorkItems.clear();
    m_currentProposalMaterials.clear();
    m_expectedPrimaryFilename.clear();
    m_expectedAnalysisReferenceFilename.clear();
    m_referenceSourcePage.clear();
    m_pendingLocalImagePaths.clear();
    m_preparedLocalImages.clear();

    if (m_errorLabel) {
        m_errorLabel->clear();
        m_errorLabel->hide();
    }

    m_titleLabel->setText("Zatim neni aktivni zakazka");
    m_subtitleLabel->setText("Vyber rozpracovanou zakazku v levem panelu projektu.");
    m_statusValueLabel->setText("-");
    m_addressValueLabel->setText("-");
    m_scopeValueLabel->setText("-");
    m_areaValueLabel->setText("-");
    m_proposalStatusValueLabel->setText("-");
    m_workflowStatusValueLabel->setText("-");
    m_workflowBlockingReasonsValueLabel->setText("bez aktivnich blokaci");
    m_referenceTestContextLabel->clear();
    m_referenceTestContextLabel->hide();
    m_proposalSubjectEdit->clear();
    m_proposalSummaryEdit->setPlainText("Po nahrani fotek se tady ukaze prvni serverovy navrh k editaci.");
    m_proposalLaborCostEdit->clear();
    m_proposalMaterialCostEdit->clear();
    if (m_proposalTransportCostEdit) m_proposalTransportCostEdit->clear();
    m_proposalAmortizationEdit->clear();
    m_proposalMarginEdit->clear();
    m_proposalTotalValueLabel->setText("-");
    m_proposalSupplierEdit->clear();
    m_proposalCompanyEdit->clear();
    m_finalProposalStatusValueLabel->setText("zatim nevytvoreno");
    m_finalProposalVersionValueLabel->setText("-");
    m_finalProposalSubjectValueLabel->setText("-");
    m_finalProposalSummaryValueLabel->setText("Po potvrzeni server vytvori finalni verzi a automaticky pripravi DOCX i PDF.");
    m_finalProposalTotalValueLabel->setText("-");
    if (m_proposalWorkItemsList) {
        m_proposalWorkItemsList->setText(
            QString::fromUtf8("Navr\u017een\u00e9 kroky se objev\u00ed po serverov\u00e9m zpracov\u00e1n\u00ed fotek."));
    }
    m_currentProposalMaterialItems.clear();
    if (m_proposalMaterialsList) {
        m_proposalMaterialsList->clear();
        m_proposalMaterialsList->addItem(
            QString::fromUtf8("Navr\u017een\u00e9 materi\u00e1ly se objev\u00ed po serverov\u00e9m zpracov\u00e1n\u00ed fotek."));
    }
    if (m_analysisObjectTypeLabel) { m_analysisObjectTypeLabel->setText("-"); }
    if (m_analysisAreaLabel) { m_analysisAreaLabel->setText("-"); }
    if (m_analysisSurfaceConditionLabel) { m_analysisSurfaceConditionLabel->setText("-"); }
    if (m_analysisRecommendedScopeLabel) { m_analysisRecommendedScopeLabel->setText("-"); }
    if (m_analysisDurationLabel) { m_analysisDurationLabel->setText("-"); }
    if (m_analysisWorkflowList) { m_analysisWorkflowList->clear(); }
    if (m_analysisMaterialsList) { m_analysisMaterialsList->clear(); }
    if (m_quoteEconomyValueLabel) { m_quoteEconomyValueLabel->setText("-"); }
    if (m_quoteStandardValueLabel) { m_quoteStandardValueLabel->setText("-"); }
    if (m_quotePremiumValueLabel) { m_quotePremiumValueLabel->setText("-"); }

    // ── Dashboard widget resets ───────────────────────────────────────────
    if (m_dashPhotoLabel) {
        m_dashPhotoLabel->clear();
        m_dashPhotoLabel->setText(QString::fromUtf8("Vyberte zak\u00e1zku pro zobrazen\u00ed hlavn\u00ed fotografie."));
    }
    if (m_dashObjTypeLabel) m_dashObjTypeLabel->setText("-");
    if (m_dashAreaLabel) m_dashAreaLabel->setText("-");
    if (m_dashSurfaceLabel) m_dashSurfaceLabel->setText("-");
    if (m_dashScopeLabel) m_dashScopeLabel->setText("-");
    if (m_dashDurationLabel) m_dashDurationLabel->setText("-");
    if (m_dashLaborLabel) m_dashLaborLabel->setText("-");
    if (m_dashMaterialLabel) m_dashMaterialLabel->setText("-");
    if (m_dashTransportLabel) m_dashTransportLabel->setText("-");
    if (m_dashMarginLabel) m_dashMarginLabel->setText("-");
    if (m_dashTotalLabel) m_dashTotalLabel->setText("-");
    if (m_dashWorkflowList) {
        m_dashWorkflowList->clear();
        m_dashWorkflowList->addItem(QString::fromUtf8("Postup pr\u00e1ce bude k dispozici po dokon\u010den\u00ed anal\u00fdzy."));
    }
    if (m_dashRunAnalysisButton) m_dashRunAnalysisButton->setEnabled(false);

    if (m_saveAsButton) {
        m_saveAsButton->setEnabled(false);
    }
    if (m_newVariantButton) {
        m_newVariantButton->setEnabled(false);
    }
    if (m_sendCaseButton) {
        m_sendCaseButton->setEnabled(false);
        m_sendCaseButton->setToolTip(QString());
    }
    if (m_runAnalysisButton) {
        m_runAnalysisButton->setEnabled(false);
    }
    if (m_saveProposalButton) {
        m_saveProposalButton->setEnabled(false);
    }
    if (m_createFinalProposalButton) {
        m_createFinalProposalButton->setEnabled(false);
        m_createFinalProposalButton->setToolTip(QString());
    }

    setImageHintMessage("Po vyberu aktivni zakazky se sem nactou fotky a jejich metadata.");
    updateImagesPanel();
    updatePendingLocalImagesPanel();
}

void CaseDetailView::saveProposalDraft()
{
    if (m_caseId.isEmpty()) {
        return;
    }

    ApiService apiService;
    ProposalDraftPatchDto payload{
        .subject = m_proposalSubjectEdit ? m_proposalSubjectEdit->text().trimmed() : QString(),
        .summary = m_proposalSummaryEdit ? m_proposalSummaryEdit->toPlainText().trimmed() : QString(),
        .materialCost = readDoubleFromEdit(m_proposalMaterialCostEdit),
        .laborCost = readDoubleFromEdit(m_proposalLaborCostEdit),
        .transportCost = readDoubleFromEdit(m_proposalTransportCostEdit),
        .amortization = readDoubleFromEdit(m_proposalAmortizationEdit),
        .margin = readDoubleFromEdit(m_proposalMarginEdit),
        .recommendedSupplier = m_proposalSupplierEdit ? m_proposalSupplierEdit->text().trimmed() : QString(),
        .recommendedCompany = m_proposalCompanyEdit ? m_proposalCompanyEdit->text().trimmed() : QString(),
    };

    QString errorMessage;
    const auto updatedCase = apiService.updateCaseProposalDraft(m_caseId, payload, &errorMessage);
    if (ApiService::sessionExpired()) { emit sessionExpired(); return; }
    if (updatedCase.id.isEmpty()) {
        m_errorLabel->setText(errorMessage.isEmpty() ? "Nepodarilo se ulozit navrh nabidky." : errorMessage);
        m_errorLabel->show();
        return;
    }

    m_errorLabel->hide();
    applyCaseData(updatedCase);
    setImageHintMessage("Navrh nabidky byl ulozen na server a znovu nacten.");
}

void CaseDetailView::createFinalProposal()
{
    if (m_caseId.isEmpty()) {
        return;
    }

    QMessageBox msgBox(this);
    msgBox.setWindowTitle(QString::fromUtf8("Vytvo\u0159it fin\u00e1ln\u00ed verzi"));
    msgBox.setText(QString::fromUtf8("Ze sou\u010dasn\u00e9ho n\u00e1vrhu vznikne fin\u00e1ln\u00ed verze a server k n\u00ed automaticky p\u0159iprav\u00ed DOCX i PDF. Pokra\u010dovat?"));
    msgBox.setIcon(QMessageBox::Question);
    auto *btnAno = msgBox.addButton(QString::fromUtf8("Ano"), QMessageBox::YesRole);
    msgBox.addButton(QString::fromUtf8("Ne"), QMessageBox::NoRole);
    msgBox.setDefaultButton(btnAno);
    msgBox.exec();
    if (msgBox.clickedButton() != btnAno) {
        return;
    }

    ApiService apiService;
    QString errorMessage;
    const auto updatedCase = apiService.createCaseFinalProposal(m_caseId, &errorMessage);
    if (ApiService::sessionExpired()) { emit sessionExpired(); return; }
    if (updatedCase.id.isEmpty()) {
        m_errorLabel->setText(errorMessage.isEmpty() ? "Nepodarilo se vytvorit finalni verzi." : errorMessage);
        m_errorLabel->show();
        return;
    }

    m_errorLabel->hide();
    applyCaseData(updatedCase);
    setImageHintMessage("Finalni verze byla vytvorena. Server k ni pripravil DOCX i PDF.");
}

void CaseDetailView::updateImagesPanel()
{
    if (m_thumbnailStripLayout) {
        while (m_thumbnailStripLayout->count() > 0) {
            auto *item = m_thumbnailStripLayout->takeAt(0);
            if (item->widget()) {
                item->widget()->deleteLater();
            }
            delete item;
        }
    }
    m_thumbnailButtons.clear();

    QString preferredImageId = m_selectedImageId;
    if (!preferredImageId.isEmpty()) {
        const bool preferredExists = std::any_of(m_images.begin(), m_images.end(), [&preferredImageId](const ImageDto &image) {
            return image.id == preferredImageId;
        });
        if (!preferredExists) {
            preferredImageId.clear();
        }
    }
    if (preferredImageId.isEmpty()) {
        const auto primaryImageIt = std::find_if(m_images.begin(), m_images.end(), [](const ImageDto &image) {
            return image.isPrimary;
        });
        if (primaryImageIt != m_images.end()) {
            preferredImageId = primaryImageIt->id;
        } else if (!m_images.empty()) {
            preferredImageId = m_images.front().id;
        }
    }

    ApiService apiService;
    for (const auto &image : m_images) {
        QStringList tooltipLines;
        tooltipLines << image.originalFilename;
        if (!image.processingStatus.isEmpty()) {
            tooltipLines << QString("stav: %1").arg(serverProcessingStatusLabel(image.processingStatus));
        }
        if (image.isPrimary) {
            tooltipLines << "vychozi";
        }
        if (image.isAnalysisReference) {
            tooltipLines << "analyza";
        }

        auto *thumbnailButton = new QPushButton(m_thumbnailStripWidget);
        thumbnailButton->setObjectName("thumbnailButton");
        thumbnailButton->setCheckable(true);
        thumbnailButton->setToolTip(tooltipLines.join("\n"));
        thumbnailButton->setCursor(Qt::PointingHandCursor);
        thumbnailButton->setProperty("imageId", image.id);

        QString previewErrorMessage;
        const auto previewData = apiService.fetchImageData(image.previewUrl, &previewErrorMessage);
        QPixmap previewPixmap;
        if (!previewData.isEmpty() && previewPixmap.loadFromData(previewData)) {
            thumbnailButton->setIcon(QIcon(previewPixmap.scaled(
                QSize(120, 90),
                Qt::KeepAspectRatio,
                Qt::SmoothTransformation)));
            thumbnailButton->setIconSize(QSize(120, 90));
        }

        connect(thumbnailButton, &QPushButton::clicked, this, [this, imageId = image.id]() {
            setSelectedImageById(imageId);
        });

        m_thumbnailStripLayout->addWidget(thumbnailButton);
        m_thumbnailButtons.push_back(thumbnailButton);
    }

    if (m_thumbnailStripWidget) {
        m_thumbnailStripWidget->adjustSize();
    }

    if (!preferredImageId.isEmpty()) {
        m_selectedImageId = preferredImageId;
    } else {
        m_selectedImageId.clear();
    }

    updateThumbnailSelectionState();
    updateImageActionButtons();
    showImagePreview(selectedImage());
    updateReferenceTestContextLabel();
}

void CaseDetailView::updateReferenceTestContextLabel()
{
    if (!m_referenceTestContextLabel) {
        return;
    }

    if (!m_isReferenceDataset) {
        m_referenceTestContextLabel->clear();
        m_referenceTestContextLabel->hide();
        return;
    }

    QString actualPrimaryFilename;
    QString actualAnalysisReferenceFilename;
    for (const auto &image : m_images) {
        if (actualPrimaryFilename.isEmpty() && image.isPrimary) {
            actualPrimaryFilename = image.originalFilename;
        }
        if (actualAnalysisReferenceFilename.isEmpty() && image.isAnalysisReference) {
            actualAnalysisReferenceFilename = image.originalFilename;
        }
    }

    QStringList contextParts;
    const auto overallStatus = overallReferenceTestStatus(
        m_expectedScope,
        m_currentRepairScope,
        m_expectedPrimaryFilename,
        actualPrimaryFilename,
        m_expectedAnalysisReferenceFilename,
        actualAnalysisReferenceFilename,
        m_currentProposalWorkItems,
        m_currentProposalMaterials);
    if (!overallStatus.isEmpty()) {
        contextParts << QString("souhrn: %1").arg(overallStatus);
    }
    if (!m_expectedScope.isEmpty()) {
        contextParts << QString("scope: %1").arg(matchLabel(m_expectedScope, m_currentRepairScope));
        const auto workItemsMatch = proposalWorkItemsMatchLabel(m_expectedScope, m_currentProposalWorkItems);
        if (!workItemsMatch.isEmpty()) {
            contextParts << QString("navrzene kroky: %1").arg(workItemsMatch);
        }
        const auto materialsMatch = proposalMaterialsMatchLabel(m_expectedScope, m_currentProposalMaterials);
        if (!materialsMatch.isEmpty()) {
            contextParts << QString("navrzene materialy: %1").arg(materialsMatch);
        }
    }
    if (!m_expectedPrimaryFilename.isEmpty()) {
        contextParts << QString("hlavni fotka: %1").arg(matchLabel(m_expectedPrimaryFilename, actualPrimaryFilename));
    }
    if (!m_expectedAnalysisReferenceFilename.isEmpty()) {
        contextParts << QString("analyza: %1").arg(matchLabel(m_expectedAnalysisReferenceFilename, actualAnalysisReferenceFilename));
    }
    if (!m_referenceSourcePage.isEmpty()) {
        contextParts << QString("zdroj: %1").arg(m_referenceSourcePage);
    }

    m_referenceTestContextLabel->setText(contextParts.join(" | "));
    m_referenceTestContextLabel->setVisible(!contextParts.isEmpty());
}

void CaseDetailView::updateThumbnailSelectionState()
{
    for (auto *button : m_thumbnailButtons) {
        if (!button) {
            continue;
        }
        const bool isSelected = button->property("imageId").toString() == m_selectedImageId;
        button->setChecked(isSelected);
        button->setProperty("selected", isSelected);
        button->style()->unpolish(button);
        button->style()->polish(button);
    }
}

void CaseDetailView::setSelectedImageById(const QString &imageId, bool autoPromoteToPrimary)
{
    if (imageId.isEmpty()) {
        m_selectedImageId.clear();
        updateThumbnailSelectionState();
        updateImageActionButtons();
        setPrimaryImagePlaceholder("Vyber obrazek z miniatur.");
        m_primaryImageLabel->setText("Vychozi fotka pro analyzu: -");
        return;
    }

    const auto imageIt = std::find_if(m_images.begin(), m_images.end(), [&imageId](const ImageDto &image) {
        return image.id == imageId;
    });
    if (imageIt == m_images.end()) {
        return;
    }

    m_selectedImageId = imageId;
    updateThumbnailSelectionState();
    updateImageActionButtons();
    showImagePreview(&(*imageIt));
    if (autoPromoteToPrimary) {
        autoSetDisplayedImageAsPrimary();
    }
}

void CaseDetailView::updateImageActionButtons()
{
    const bool hasSelection = !m_selectedImageId.isEmpty();
    const auto imageIt = std::find_if(m_images.begin(), m_images.end(), [this](const ImageDto &image) {
        return image.id == m_selectedImageId;
    });
    const auto selectedIndex = imageIt != m_images.end()
        ? static_cast<int>(std::distance(m_images.begin(), imageIt))
        : -1;

    if (m_moveUpButton) {
        m_moveUpButton->setEnabled(hasSelection && selectedIndex > 0);
    }
    if (m_moveDownButton) {
        m_moveDownButton->setEnabled(hasSelection && selectedIndex >= 0 && selectedIndex < static_cast<int>(m_images.size()) - 1);
    }
    if (m_setPrimaryButton) {
        m_setPrimaryButton->setEnabled(hasSelection && imageIt != m_images.end() && !imageIt->isPrimary);
    }
    if (m_setAnalysisReferenceButton) {
        m_setAnalysisReferenceButton->setEnabled(hasSelection && imageIt != m_images.end() && !imageIt->isAnalysisReference);
    }
}

void CaseDetailView::setImageHintMessage(const QString &message, bool isError)
{
    m_imageHintLabel->setText(message);
    m_imageHintLabel->setObjectName(isError ? "errorLabel" : "hintLabel");
    m_imageHintLabel->style()->unpolish(m_imageHintLabel);
    m_imageHintLabel->style()->polish(m_imageHintLabel);
}

void CaseDetailView::selectAdjacentImage(int step)
{
    if (m_images.empty()) {
        return;
    }

    const auto imageIt = std::find_if(m_images.begin(), m_images.end(), [this](const ImageDto &image) {
        return image.id == m_selectedImageId;
    });
    int selectedIndex = imageIt != m_images.end()
        ? static_cast<int>(std::distance(m_images.begin(), imageIt))
        : 0;
    selectedIndex += step;
    if (selectedIndex < 0 || selectedIndex >= static_cast<int>(m_images.size())) {
        return;
    }

    setSelectedImageById(m_images[static_cast<size_t>(selectedIndex)].id);
}

void CaseDetailView::autoSetDisplayedImageAsPrimary()
{
    const auto *image = selectedImage();
    if (!image || m_caseId.isEmpty() || image->isPrimary) {
        return;
    }

    setSelectedImageAsPrimary();
}

void CaseDetailView::selectLocalImages()
{
    const auto selectedFiles = QFileDialog::getOpenFileNames(
        this,
        "Vyber fotky z PC",
        QString(),
        "Images (*.jpg *.jpeg *.png *.webp *.bmp)");

    if (selectedFiles.isEmpty()) {
        return;
    }

    m_pendingLocalImagePaths = selectedFiles;
    m_preparedLocalImages.clear();
    updatePendingLocalImagesPanel();
    setImageHintMessage(QString("Vybrano %1 fotek z PC pro dalsi zpracovani.").arg(selectedFiles.size()));
}

void CaseDetailView::convertPendingLocalImages()
{
    if (m_pendingLocalImagePaths.isEmpty()) {
        return;
    }

    m_preparedLocalImages.clear();
    m_preparedLocalImages.reserve(static_cast<size_t>(m_pendingLocalImagePaths.size()));

    for (const auto &path : m_pendingLocalImagePaths) {
        LocalPreparedImage preparedImage;
        preparedImage.sourcePath = path;
        preparedImage.mimeType = "image/jpeg";

        const QFileInfo fileInfo(path);
        preparedImage.outputFilename = fileInfo.completeBaseName().isEmpty()
            ? "prepared-image.jpg"
            : fileInfo.completeBaseName() + ".jpg";

        QImageReader reader(path);
        reader.setAutoTransform(true);
        const QSize targetSize = scaledImageSize(reader.size(), kPreparedImageMaxEdge);
        if (targetSize.isValid()) {
            reader.setScaledSize(targetSize);
        }

        const QImage image = reader.read();
        if (image.isNull()) {
            preparedImage.errorMessage = reader.errorString().isEmpty()
                ? "Soubor se nepodarilo nacist."
                : reader.errorString();
            preparedImage.state = LocalImageState::Error;
            m_preparedLocalImages.push_back(std::move(preparedImage));
            continue;
        }

        QByteArray convertedBytes;
        QBuffer buffer(&convertedBytes);
        buffer.open(QIODevice::WriteOnly);

        QImageWriter writer(&buffer, "jpg");
        writer.setQuality(kPreparedImageQuality);
        if (!writer.write(image)) {
            preparedImage.errorMessage = writer.errorString().isEmpty()
                ? "Soubor se nepodarilo zkonvertovat."
                : writer.errorString();
            preparedImage.state = LocalImageState::Error;
            m_preparedLocalImages.push_back(std::move(preparedImage));
            continue;
        }

        preparedImage.width = image.width();
        preparedImage.height = image.height();
        preparedImage.byteSize = convertedBytes.size();
        preparedImage.payload = convertedBytes;
        preparedImage.state = LocalImageState::ReadyToUpload;
        m_preparedLocalImages.push_back(std::move(preparedImage));
    }

    updatePendingLocalImagesPanel();

    const int readyCount = static_cast<int>(std::count_if(
        m_preparedLocalImages.begin(),
        m_preparedLocalImages.end(),
        [](const LocalPreparedImage &image) { return image.state == LocalImageState::ReadyToUpload; }));

    if (readyCount == static_cast<int>(m_preparedLocalImages.size())) {
        setImageHintMessage(QString::fromUtf8("P\u0159ipraveno %1 fotek, nahr\u00e1v\u00e1m na server\u2026").arg(readyCount));
        uploadPreparedLocalImages();
    } else {
        setImageHintMessage(
            QString::fromUtf8("P\u0159ipraveno %1 z %2 fotek. Zbytek se nepoda\u0159ilo zpracovat.")
                .arg(readyCount)
                .arg(m_preparedLocalImages.size()),
            readyCount == 0);
        if (readyCount > 0) {
            uploadPreparedLocalImages();
        }
    }
}

void CaseDetailView::updatePendingLocalImagesPanel()
{
    if (!m_pendingLocalImagesList || !m_pendingLocalImagesLabel) {
        return;
    }

    m_pendingLocalImagesList->clear();
    if (!m_preparedLocalImages.empty()) {
        for (const auto &preparedImage : m_preparedLocalImages) {
            QString itemLabel = QFileInfo(preparedImage.sourcePath).fileName();
            if (preparedImage.state == LocalImageState::ReadyToUpload) {
                itemLabel += QString("  |  pripraveno k odeslani  |  JPEG  |  %1 x %2  |  %3 KB")
                                 .arg(preparedImage.width)
                                 .arg(preparedImage.height)
                                 .arg(std::max(1, preparedImage.byteSize / 1024));
                if (!preparedImage.errorMessage.isEmpty()) {
                    itemLabel += QString("  |  posledni pokus selhal: %1").arg(preparedImage.errorMessage);
                }
            } else if (preparedImage.state == LocalImageState::Uploading) {
                itemLabel += QString("  |  odesila se  |  JPEG  |  %1 x %2  |  %3 KB")
                                 .arg(preparedImage.width)
                                 .arg(preparedImage.height)
                                 .arg(std::max(1, preparedImage.byteSize / 1024));
            } else if (preparedImage.state == LocalImageState::Uploaded) {
                itemLabel += QString("  |  odeslano  |  JPEG  |  %1 x %2  |  %3 KB")
                                 .arg(preparedImage.width)
                                 .arg(preparedImage.height)
                                 .arg(std::max(1, preparedImage.byteSize / 1024));
            } else {
                itemLabel += QString("  |  chyba  |  %1").arg(preparedImage.errorMessage);
            }
            m_pendingLocalImagesList->addItem(itemLabel);
        }
    } else {
        for (const auto &path : m_pendingLocalImagePaths) {
            m_pendingLocalImagesList->addItem(QFileInfo(path).fileName() + "  |  ceka na konverzi");
        }
    }

    if (m_pendingLocalImagePaths.isEmpty()) {
        m_pendingLocalImagesLabel->setText("Vybrane fotky z PC: zatim nic.");
    } else if (!m_preparedLocalImages.empty()) {
        const int readyCount = static_cast<int>(std::count_if(
            m_preparedLocalImages.begin(),
            m_preparedLocalImages.end(),
            [](const LocalPreparedImage &image) { return image.state == LocalImageState::ReadyToUpload; }));
        const int uploadingCount = static_cast<int>(std::count_if(
            m_preparedLocalImages.begin(),
            m_preparedLocalImages.end(),
            [](const LocalPreparedImage &image) { return image.state == LocalImageState::Uploading; }));
        const int uploadedCount = static_cast<int>(std::count_if(
            m_preparedLocalImages.begin(),
            m_preparedLocalImages.end(),
            [](const LocalPreparedImage &image) { return image.state == LocalImageState::Uploaded; }));
        const int errorCount = static_cast<int>(std::count_if(
            m_preparedLocalImages.begin(),
            m_preparedLocalImages.end(),
            [](const LocalPreparedImage &image) { return image.state == LocalImageState::Error; }));
        m_pendingLocalImagesLabel->setText(
            QString("Vybrane fotky z PC: %1 souboru, %2 pripravenych, %3 odesilanych, %4 odeslanych, %5 s chybou.")
                .arg(m_pendingLocalImagePaths.size())
                .arg(readyCount)
                .arg(uploadingCount)
                .arg(uploadedCount)
                .arg(errorCount));
    } else {
        m_pendingLocalImagesLabel->setText(
            QString("Vybrane fotky z PC: %1 souboru pripravenych ke konverzi.")
                .arg(m_pendingLocalImagePaths.size()));
    }

    const bool hasAnyPending = !m_pendingLocalImagePaths.isEmpty() || !m_preparedLocalImages.empty();
    if (m_pendingLocalImagesList) {
        m_pendingLocalImagesList->setVisible(hasAnyPending);
    }
    if (m_convertImagesButton) {
        m_convertImagesButton->setEnabled(!m_pendingLocalImagePaths.isEmpty());
    }
}

void CaseDetailView::uploadPreparedLocalImages()
{
    if (m_caseId.isEmpty()) {
        return;
    }

    std::vector<UploadImageDto> uploadImages;
    std::vector<size_t> uploadIndexes;
    for (size_t index = 0; index < m_preparedLocalImages.size(); ++index) {
        const auto &preparedImage = m_preparedLocalImages[index];
        if (preparedImage.state != LocalImageState::ReadyToUpload || preparedImage.payload.isEmpty()) {
            continue;
        }

        uploadIndexes.push_back(index);
        uploadImages.push_back(
            {
                .originalFilename = preparedImage.outputFilename,
                .mimeType = preparedImage.mimeType,
                .payload = preparedImage.payload,
            });
    }

    if (uploadImages.empty()) {
        setImageHintMessage("Nejsou pripravene zadne fotky k odeslani.", true);
        return;
    }

    for (const size_t index : uploadIndexes) {
        m_preparedLocalImages[index].state = LocalImageState::Uploading;
        m_preparedLocalImages[index].errorMessage.clear();
    }
    updatePendingLocalImagesPanel();
    setImageHintMessage(QString("Odesilam %1 fotek na server.").arg(uploadImages.size()));
    QApplication::processEvents();

    ApiService apiService;
    QString errorMessage;
    if (!apiService.uploadCaseImages(m_caseId, uploadImages, &errorMessage)) {
        if (ApiService::sessionExpired()) { emit sessionExpired(); return; }
        for (const size_t index : uploadIndexes) {
            m_preparedLocalImages[index].state = LocalImageState::ReadyToUpload;
            m_preparedLocalImages[index].errorMessage = errorMessage;
        }
        updatePendingLocalImagesPanel();
        setImageHintMessage(errorMessage, true);
        return;
    }

    for (const size_t index : uploadIndexes) {
        m_preparedLocalImages[index].state = LocalImageState::Uploaded;
        m_preparedLocalImages[index].payload.clear();
        m_preparedLocalImages[index].errorMessage.clear();
    }

    QString refreshErrorMessage;
    if (!refreshImagesFromBackend(&refreshErrorMessage)) {
        setImageHintMessage(refreshErrorMessage, true);
        return;
    }

    updateImagesPanel();
    updatePendingLocalImagesPanel();
    setCase(m_caseId);

    if (hasPendingServerImageStatuses(m_images)) {
        startImageStatusPolling();
        setImageHintMessage(
            QString("Na server bylo odeslano %1 fotek. Backend stale zpracovava: %2.")
                .arg(uploadImages.size())
                .arg(summarizeServerImageStatuses(m_images)));
        return;
    }

    stopImageStatusPolling();
    setImageHintMessage(
        QString("Na server bylo odeslano %1 fotek. Backend hlasi: %2.")
            .arg(uploadImages.size())
            .arg(summarizeServerImageStatuses(m_images)));
}

void CaseDetailView::downloadExport(const QString &exportType)
{
    if (m_caseId.isEmpty()) {
        return;
    }

    setImageHintMessage(QString("Pripravuji export: %1...").arg(exportType));
    QApplication::processEvents();

    ApiService apiService;
    QString errorMessage;
    const auto exportResult = apiService.triggerExport(m_caseId, exportType, &errorMessage);
    if (ApiService::sessionExpired()) { emit sessionExpired(); return; }
    if (exportResult.downloadUrl.isEmpty()) {
        setImageHintMessage(
            errorMessage.isEmpty() ? "Export se nezdaril — backend nevratil download URL." : errorMessage,
            true);
        return;
    }

    const auto fileBytes = apiService.downloadExportFile(exportResult.downloadUrl, &errorMessage);
    if (ApiService::sessionExpired()) { emit sessionExpired(); return; }
    if (fileBytes.isEmpty()) {
        setImageHintMessage(
            errorMessage.isEmpty() ? "Stazeni souboru se nezdarilo." : errorMessage,
            true);
        return;
    }

    const QString tempDir =
        QStandardPaths::writableLocation(QStandardPaths::TempLocation) + "/NovuBuilder";
    QDir().mkpath(tempDir);

    const QString fileName = exportResult.fileName.isEmpty()
        ? QString("%1-%2.bin").arg(m_caseId, exportType)
        : exportResult.fileName;
    const QString filePath = tempDir + "/" + fileName;

    QFile file(filePath);
    if (!file.open(QIODevice::WriteOnly)) {
        setImageHintMessage("Nepodarilo se ulozit soubor do temp adresare.", true);
        return;
    }
    file.write(fileBytes);
    file.close();

    QDesktopServices::openUrl(QUrl::fromLocalFile(filePath));
    setImageHintMessage(QString("Export byl ulozen a otevren: %1").arg(fileName));
}

void CaseDetailView::exportAsZip()
{
    if (m_caseId.isEmpty() || m_currentCase.id.isEmpty()) {
        return;
    }

    // Sanitize title for filename
    QString safeTitle = m_currentCase.title.isEmpty() ? m_caseId : m_currentCase.title;
    for (const QChar ch : {'\\', '/', ':', '*', '?', '"', '<', '>', '|'}) {
        safeTitle.replace(ch, '_');
    }
    const QString defaultName = QString("Zakazka_%1.zip").arg(safeTitle);

    const QString zipPath = QFileDialog::getSaveFileName(
        this,
        QString::fromUtf8("Ulo\u017eit zak\u00e1zku jako ZIP"),
        QStandardPaths::writableLocation(QStandardPaths::DocumentsLocation) + "/" + defaultName,
        QString::fromUtf8("ZIP archiv (*.zip)")
    );
    if (zipPath.isEmpty()) {
        return;
    }

    setImageHintMessage(QString::fromUtf8("P\u0159ipravuji ZIP export\u2026"));
    QApplication::processEvents();

    // Prepare temp working directory
    const QString tempBase = QStandardPaths::writableLocation(QStandardPaths::TempLocation)
        + "/NovuBuilder/export_" + m_caseId;
    QDir(tempBase).removeRecursively();
    QDir().mkpath(tempBase + "/fotky");

    ApiService apiService;
    QString errorMessage;
    int errors = 0;

    // 1. Download DOCX (final proposal)
    const auto exportResult = apiService.triggerExport(m_caseId, "proposal-docx", &errorMessage);
    if (ApiService::sessionExpired()) { emit sessionExpired(); return; }
    if (!exportResult.downloadUrl.isEmpty()) {
        const auto docxBytes = apiService.downloadExportFile(exportResult.downloadUrl, &errorMessage);
        if (ApiService::sessionExpired()) { emit sessionExpired(); return; }
        if (!docxBytes.isEmpty()) {
            const QString docxName = exportResult.fileName.isEmpty()
                ? QString("Nabidka_%1.docx").arg(safeTitle)
                : exportResult.fileName;
            QFile docxFile(tempBase + "/" + docxName);
            if (docxFile.open(QIODevice::WriteOnly)) {
                docxFile.write(docxBytes);
                docxFile.close();
            }
        } else {
            ++errors;
        }
    } else {
        ++errors;
    }

    // 2. Download images (previews)
    for (const auto &image : m_images) {
        if (image.previewUrl.isEmpty()) { continue; }
        const auto imgBytes = apiService.fetchImageData(image.previewUrl, &errorMessage);
        if (ApiService::sessionExpired()) { emit sessionExpired(); return; }
        if (imgBytes.isEmpty()) { ++errors; continue; }
        QString imgName = image.originalFilename.isEmpty()
            ? image.id + ".jpg"
            : image.originalFilename;
        QFile imgFile(tempBase + "/fotky/" + imgName);
        if (imgFile.open(QIODevice::WriteOnly)) {
            imgFile.write(imgBytes);
            imgFile.close();
        }
    }

    // 3. Create JSON data file
    QJsonObject json;
    json["id"]           = m_currentCase.id;
    json["title"]        = m_currentCase.title;
    json["status"]       = m_currentCase.status;
    json["addressLabel"] = m_currentCase.addressLabel;
    json["description"]  = m_currentCase.description;
    json["propertyType"] = m_currentCase.propertyType;
    json["repairScope"]  = m_currentCase.repairScope;
    json["createdBy"]    = m_currentCase.createdByName;
    if (m_currentCase.hasAnalysis) {
        QJsonObject analysis;
        analysis["objectType"]       = m_currentCase.analysisObjectType;
        analysis["surfaceCondition"] = m_currentCase.analysisSurfaceCondition;
        analysis["recommendedScope"] = m_currentCase.analysisRecommendedScope;
        analysis["estimatedAreaSqm"] = m_currentCase.analysisEstimatedAreaSqm;
        analysis["durationDays"]     = m_currentCase.analysisDurationDays;
        analysis["laborHours"]       = m_currentCase.analysisLaborHours;
        json["analysis"] = analysis;
    }
    {
        QJsonObject proposal;
        proposal["subject"]             = m_currentCase.proposalSubject;
        proposal["summary"]             = m_currentCase.proposalSummary;
        proposal["materialCost"]        = m_currentCase.proposalMaterialCostLabel;
        proposal["laborCost"]           = m_currentCase.proposalLaborCostLabel;
        proposal["transportCost"]       = m_currentCase.proposalTransportCostLabel;
        proposal["totalPrice"]          = m_currentCase.proposalTotalPriceLabel;
        proposal["recommendedSupplier"] = m_currentCase.proposalRecommendedSupplier;
        json["proposal"] = proposal;
    }
    if (!m_currentCase.finalProposalStatus.isEmpty()) {
        QJsonObject finalProposal;
        finalProposal["status"]     = m_currentCase.finalProposalStatus;
        finalProposal["subject"]    = m_currentCase.finalProposalSubject;
        finalProposal["summary"]    = m_currentCase.finalProposalSummary;
        finalProposal["totalPrice"] = m_currentCase.finalProposalTotalPriceLabel;
        json["finalProposal"] = finalProposal;
    }
    QFile jsonFile(tempBase + "/zakazka.json");
    if (jsonFile.open(QIODevice::WriteOnly | QIODevice::Text)) {
        jsonFile.write(QJsonDocument(json).toJson(QJsonDocument::Indented));
        jsonFile.close();
    }

    // 4. Create ZIP via PowerShell Compress-Archive
    QFile::remove(zipPath);
    const QString psCmd = QString(
        "Compress-Archive -Path '%1\\*' -DestinationPath '%2' -Force"
    ).arg(QDir::toNativeSeparators(tempBase), QDir::toNativeSeparators(zipPath));

    QProcess process;
    process.start("powershell",
        QStringList() << "-NoProfile" << "-NonInteractive" << "-Command" << psCmd);
    process.waitForFinished(30000);

    QDir(tempBase).removeRecursively();

    if (!QFile::exists(zipPath)) {
        setImageHintMessage(QString::fromUtf8("ZIP se nepoda\u0159ilo vytvo\u0159it."), true);
        return;
    }

    const QString resultMsg = errors > 0
        ? QString::fromUtf8("ZIP ulo\u017een s %1 chybami: %2").arg(errors).arg(zipPath)
        : QString::fromUtf8("ZIP ulo\u017een: %1").arg(zipPath);
    setImageHintMessage(resultMsg, errors > 0);
    QDesktopServices::openUrl(QUrl::fromLocalFile(QFileInfo(zipPath).absolutePath()));
}

void CaseDetailView::setSelectedImageAsPrimary()
{
    const auto *image = selectedImage();
    if (!image || m_caseId.isEmpty()) {
        return;
    }

    ApiService apiService;
    CaseDetailViewModel viewModel;
    if (!viewModel.setPrimaryImage(m_caseId, image->id, apiService)) {
        if (ApiService::sessionExpired()) { emit sessionExpired(); return; }
        setImageHintMessage(viewModel.imageErrorMessage(), true);
        return;
    }

    const auto images = viewModel.loadCaseImages(m_caseId, apiService);
    if (ApiService::sessionExpired()) { emit sessionExpired(); return; }
    if (!viewModel.imageErrorMessage().isEmpty()) {
        setImageHintMessage(viewModel.imageErrorMessage(), true);
        return;
    }

    m_images = images;
    updateImagesPanel();
}

void CaseDetailView::setSelectedImageAsAnalysisReference()
{
    const auto *image = selectedImage();
    if (!image || m_caseId.isEmpty()) {
        return;
    }

    ApiService apiService;
    CaseDetailViewModel viewModel;
    if (!viewModel.setAnalysisReferenceImage(m_caseId, image->id, apiService)) {
        if (ApiService::sessionExpired()) { emit sessionExpired(); return; }
        setImageHintMessage(viewModel.imageErrorMessage(), true);
        return;
    }

    const auto images = viewModel.loadCaseImages(m_caseId, apiService);
    if (ApiService::sessionExpired()) { emit sessionExpired(); return; }
    if (!viewModel.imageErrorMessage().isEmpty()) {
        setImageHintMessage(viewModel.imageErrorMessage(), true);
        return;
    }

    m_images = images;
    updateImagesPanel();
    setImageHintMessage("Referencni fotka pro analyzu byla zmenena.");
}

void CaseDetailView::duplicateCase(const QString &mode)
{
    if (m_caseId.isEmpty()) {
        return;
    }

    if (m_images.empty()) {
        QMessageBox msgBoxCopy(this);
        msgBoxCopy.setWindowTitle(QString::fromUtf8("Vytvo\u0159it kop\u00edji bez fotek?"));
        msgBoxCopy.setText(QString::fromUtf8("Aktu\u00e1ln\u00ed zak\u00e1zka zat\u00edm nem\u00e1 na\u010dten\u00e9 \u017e\u00e1dn\u00e9 fotky. Nov\u00e1 zak\u00e1zka bude tak\u00e9 bez fotek.\n\nPokra\u010dovat i tak?"));
        msgBoxCopy.setIcon(QMessageBox::Question);
        auto *btnAnoCopy = msgBoxCopy.addButton(QString::fromUtf8("Ano"), QMessageBox::YesRole);
        msgBoxCopy.addButton(QString::fromUtf8("Ne"), QMessageBox::NoRole);
        msgBoxCopy.exec();
        if (msgBoxCopy.clickedButton() != btnAnoCopy) {
            return;
        }
    }

    ApiService apiService;
    QString errorMessage;
    const auto duplicatedCaseId = apiService.duplicateCase(m_caseId, mode, &errorMessage);
    if (ApiService::sessionExpired()) { emit sessionExpired(); return; }
    if (duplicatedCaseId.isEmpty()) {
        m_errorLabel->setText(errorMessage.isEmpty() ? "Nepodarilo se vytvorit kopii zakazky." : errorMessage);
        m_errorLabel->show();
        return;
    }

    m_errorLabel->hide();
    emit caseDuplicated(duplicatedCaseId);
}

void CaseDetailView::sendCurrentCase()
{
    if (m_caseId.isEmpty()) {
        return;
    }

    QMessageBox msgBoxSend(this);
    msgBoxSend.setWindowTitle(QString::fromUtf8("Odeslat zak\u00e1zku"));
    msgBoxSend.setText(QString::fromUtf8("Zak\u00e1zka \"%1\" bude ozna\u010dena jako odeslan\u00e1 a p\u0159eunuta do historie.\n\nZ\u00e1kazn\u00edk obdr\u017e\u00ed PDF na sv\u016fj email. Pokra\u010dovat?")
        .arg(m_titleLabel->text().isEmpty() ? QString::fromUtf8("Bez n\u00e1zvu") : m_titleLabel->text()));
    msgBoxSend.setIcon(QMessageBox::Question);
    auto *btnAnoSend = msgBoxSend.addButton(QString::fromUtf8("Ano, odeslat"), QMessageBox::YesRole);
    msgBoxSend.addButton(QString::fromUtf8("Ne"), QMessageBox::NoRole);
    msgBoxSend.exec();
    if (msgBoxSend.clickedButton() != btnAnoSend) {
        return;
    }

    ApiService apiService;
    QString errorMessage;
    if (!apiService.sendCase(m_caseId, &errorMessage)) {
        if (ApiService::sessionExpired()) { emit sessionExpired(); return; }
        m_errorLabel->setText(errorMessage.isEmpty() ? "Nepodarilo se odeslat zakazku." : errorMessage);
        m_errorLabel->show();
        return;
    }

    m_errorLabel->hide();
    emit caseSent(m_caseId);
}

void CaseDetailView::startImageStatusPolling()
{
    if (!m_imagePollingTimer || m_caseId.isEmpty()) {
        return;
    }

    m_remainingImagePollAttempts = kImagePollingAttemptLimit;
    if (!m_imagePollingTimer->isActive()) {
        m_imagePollingTimer->start();
    }
}

void CaseDetailView::stopImageStatusPolling()
{
    if (m_imagePollingTimer && m_imagePollingTimer->isActive()) {
        m_imagePollingTimer->stop();
    }
    m_remainingImagePollAttempts = 0;
}

void CaseDetailView::pollImageStatuses()
{
    if (m_caseId.isEmpty()) {
        stopImageStatusPolling();
        return;
    }

    if (m_remainingImagePollAttempts <= 0) {
        stopImageStatusPolling();
        setImageHintMessage(
            QString("Backend stale hlasi: %1. Detail muzes pozdeji znovu obnovit.")
                .arg(summarizeServerImageStatuses(m_images)));
        return;
    }

    --m_remainingImagePollAttempts;

    QString errorMessage;
    if (!refreshImagesFromBackend(&errorMessage)) {
        stopImageStatusPolling();
        setImageHintMessage(errorMessage, true);
        return;
    }

    updateImagesPanel();
    setCase(m_caseId);

    if (hasPendingServerImageStatuses(m_images)) {
        setImageHintMessage(
            QString("Backend stale zpracovava fotky. Aktualni stav: %1.")
                .arg(summarizeServerImageStatuses(m_images)));
        return;
    }

    stopImageStatusPolling();
    setImageHintMessage(
        QString("Zpracovani fotek je dokonceno. Stav: %1.")
            .arg(summarizeServerImageStatuses(m_images)));
}

void CaseDetailView::triggerAnalysis()
{
    if (m_caseId.isEmpty()) return;

    m_runAnalysisButton->setEnabled(false);
    m_analysisJobStatusLabel->setText("Spoustim analyzu...");
    m_analysisJobStatusLabel->show();

    ApiService apiService;
    QString errorMessage;
    const auto jobId = apiService.triggerAnalysisJob(m_caseId, &errorMessage);

    if (ApiService::sessionExpired()) { emit sessionExpired(); return; }

    if (jobId.isEmpty()) {
        m_analysisJobStatusLabel->setText(
            QString("Chyba: %1").arg(errorMessage.isEmpty() ? "Nepodarilo se spustit analyzu." : errorMessage));
        m_runAnalysisButton->setEnabled(true);
        return;
    }

    startAnalysisPolling(jobId);
}

void CaseDetailView::confirmSelectionArea()
{
    if (m_caseId.isEmpty() || m_analysisId.isEmpty()) return;
    if (!m_overlayWidget || !m_overlayWidget->hasSelection()) return;

    const auto polygon = m_overlayWidget->selectionPolygon();
    bool areaOk = false;
    const double manualArea = m_overlayAreaEdit ? m_overlayAreaEdit->text().replace(',', '.').toDouble(&areaOk) : 0.0;

    if (m_overlayConfirmButton) m_overlayConfirmButton->setEnabled(false);

    ApiService apiService;
    QString errorMessage;
    const bool ok = apiService.patchAnalysisSelection(
        m_caseId,
        m_analysisId,
        polygon,
        areaOk && manualArea > 0.0 ? manualArea : 0.0,
        &errorMessage);

    if (ApiService::sessionExpired()) { emit sessionExpired(); return; }

    if (!ok) {
        setImageHintMessage(
            QString("Chyba pri ukladani oblasti: %1")
                .arg(errorMessage.isEmpty() ? "Neznama chyba." : errorMessage),
            true);
        if (m_overlayConfirmButton) m_overlayConfirmButton->setEnabled(true);
        return;
    }

    setImageHintMessage("Oblast opravy byla ulozena.");
    m_overlayWidget->clearSelection();
    setCase(m_caseId); // znovu nacte data i s aktualizovanou plochou
}

void CaseDetailView::startAnalysisPolling(const QString &jobId)
{
    constexpr int kAnalysisPollAttemptLimit = 90; // 90 × 2s = 3 minuty
    m_analysisJobId = jobId;
    m_remainingAnalysisPollAttempts = kAnalysisPollAttemptLimit;
    m_analysisJobStatusLabel->setText("Analyza probiha... (cekam na vysledek)");
    m_analysisJobStatusLabel->show();
    if (!m_analysisPollingTimer->isActive()) {
        m_analysisPollingTimer->start();
    }
}

void CaseDetailView::stopAnalysisPolling()
{
    if (m_analysisPollingTimer && m_analysisPollingTimer->isActive()) {
        m_analysisPollingTimer->stop();
    }
    m_remainingAnalysisPollAttempts = 0;
    m_analysisJobId.clear();
}

void CaseDetailView::pollAnalysisStatus()
{
    if (m_analysisJobId.isEmpty() || m_caseId.isEmpty()) {
        stopAnalysisPolling();
        return;
    }

    if (m_remainingAnalysisPollAttempts <= 0) {
        stopAnalysisPolling();
        m_analysisJobStatusLabel->setText("Analyza trvala prilis dlouho — zkuste ji spustit znovu.");
        m_runAnalysisButton->setEnabled(true);
        return;
    }

    --m_remainingAnalysisPollAttempts;

    ApiService apiService;
    QString errorMessage;
    const auto status = apiService.getAnalysisJobStatus(m_analysisJobId, &errorMessage);

    if (ApiService::sessionExpired()) { emit sessionExpired(); return; }

    if (status == "completed") {
        stopAnalysisPolling();
        m_analysisJobStatusLabel->setText("Analyza dokoncena. Nacitam vysledky...");
        setCase(m_caseId); // reload all — fills findings tab
        m_analysisJobStatusLabel->setText("Analyza dokoncena. Vysledky jsou k dispozici.");
        m_runAnalysisButton->setEnabled(true);
    } else if (status == "failed") {
        stopAnalysisPolling();
        m_analysisJobStatusLabel->setText("Analyza selhala. Zkontrolujte fotky a zkuste znovu.");
        m_runAnalysisButton->setEnabled(true);
    } else if (status == "running") {
        m_analysisJobStatusLabel->setText(
            QString("Analyza probiha... (%1 s)")
                .arg((90 - m_remainingAnalysisPollAttempts) * 2));
    } else if (!status.isEmpty()) {
        m_analysisJobStatusLabel->setText(QString("Stav: %1").arg(status));
    } else if (!errorMessage.isEmpty()) {
        // network hiccup — just keep trying
        m_analysisJobStatusLabel->setText(
            QString("Cekam na server (%1)").arg(errorMessage));
    }
}

bool CaseDetailView::refreshImagesFromBackend(QString *errorMessage)
{
    CaseDetailViewModel viewModel;
    ApiService apiService;
    const auto images = viewModel.loadCaseImages(m_caseId, apiService);
    if (!viewModel.imageErrorMessage().isEmpty()) {
        if (errorMessage) {
            *errorMessage = viewModel.imageErrorMessage();
        }
        return false;
    }

    if (errorMessage) {
        errorMessage->clear();
    }

    m_images = images;
    return true;
}

void CaseDetailView::setPrimaryImagePreview(const QPixmap &pixmap)
{
    m_primaryImagePixmap = pixmap;
    if (m_overlayWidget) {
        m_overlayWidget->setPhoto(pixmap);
    }
    if (m_dashPhotoLabel) {
        const auto scaled = pixmap.scaledToHeight(270, Qt::SmoothTransformation);
        m_dashPhotoLabel->setPixmap(scaled);
    }
}

void CaseDetailView::setPrimaryImagePlaceholder(const QString &message)
{
    m_primaryImagePixmap = QPixmap();
    if (m_overlayWidget) {
        m_overlayWidget->setPlaceholder(message);
    }
    if (m_dashPhotoLabel) {
        m_dashPhotoLabel->clear();
        m_dashPhotoLabel->setText(
            QString::fromUtf8("Fotografie zak\u00e1zky se zobraz\u00ed po nahr\u00e1n\u00ed."));
    }
}

void CaseDetailView::updatePrimaryImagePreview()
{
    // ImageOverlayWidget handles its own scaling in paintEvent — nothing to do
}

bool CaseDetailView::eventFilter(QObject *watched, QEvent *event)
{
    if (watched == m_dashPhotoLabel && event->type() == QEvent::MouseButtonPress) {
        switchToPhotosTab();
        return true;
    }
    return QWidget::eventFilter(watched, event);
}

void CaseDetailView::showImagePreview(const ImageDto *image)
{
    if (!image) {
        m_primaryImageLabel->setText("Vychozi fotka pro analyzu: -");
        setPrimaryImagePlaceholder("Case zatim nema fotku pro preview.");
        return;
    }

    QString imageLabel = QString("Vychozi fotka pro analyzu: %1")
                             .arg(image->originalFilename.isEmpty() ? "-" : image->originalFilename);
    m_primaryImageLabel->setText(imageLabel);

    ApiService apiService;
    QString previewErrorMessage;
    const auto previewData = apiService.fetchImageData(image->previewUrl, &previewErrorMessage);

    QPixmap previewPixmap;
    if (!previewData.isEmpty() && previewPixmap.loadFromData(previewData)) {
        setPrimaryImagePreview(previewPixmap);
    } else if (!previewErrorMessage.isEmpty()) {
        setPrimaryImagePlaceholder(previewErrorMessage);
    } else {
        setPrimaryImagePlaceholder("Preview vybrane fotky neni k dispozici.");
    }
}

const ImageDto *CaseDetailView::selectedImage() const
{
    if (m_selectedImageId.isEmpty()) {
        return nullptr;
    }

    const auto imageIt = std::find_if(m_images.begin(), m_images.end(), [this](const ImageDto &image) {
        return image.id == m_selectedImageId;
    });

    return imageIt != m_images.end() ? &(*imageIt) : nullptr;
}

void CaseDetailView::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    updatePrimaryImagePreview();
}
