#include "casedetailview.h"

#include <algorithm>
#include <array>
#include <cmath>

#include <QApplication>
#include <QBuffer>
#include <QFileDialog>
#include <QFileInfo>
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
#include <QStringList>
#include <QSignalBlocker>
#include <QSizePolicy>
#include <QTimer>
#include <QVBoxLayout>

#include "services/apiservice.h"
#include "viewmodels/casedetailviewmodel.h"

namespace {
constexpr int kPreparedImageMaxEdge = 1600;
constexpr int kPreparedImageQuality = 85;
constexpr int kImagePollingIntervalMs = 1500;
constexpr int kImagePollingAttemptLimit = 8;

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

QString proposalStatusLabel(const QString &status)
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

QString finalProposalStatusLabel(const QString &status)
{
    if (status == "ready_for_export") {
        return "pripraveno pro export";
    }
    return status.isEmpty() ? "zatim nevytvoreno" : status;
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
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);

    auto *card = new QFrame(this);
    card->setObjectName("detailCard");
    auto *cardLayout = new QVBoxLayout(card);
    cardLayout->setContentsMargins(20, 20, 20, 20);
    cardLayout->setSpacing(16);

    m_titleLabel = new QLabel("Vyber aktualni zakazku", card);
    m_titleLabel->setObjectName("sectionTitle");
    m_subtitleLabel = new QLabel("Po vyberu v seznamu se sem nacte skutecny detail z backendu.", card);
    m_subtitleLabel->setObjectName("hintLabel");
    m_subtitleLabel->setWordWrap(true);
    m_errorLabel = new QLabel(card);
    m_errorLabel->setObjectName("errorLabel");
    m_errorLabel->setWordWrap(true);
    m_errorLabel->hide();

    auto *summary = new QFrame(card);
    summary->setObjectName("summaryCard");
    auto *summaryLayout = new QFormLayout(summary);
    summaryLayout->setContentsMargins(16, 16, 16, 16);
    m_statusValueLabel = new QLabel("-", summary);
    m_addressValueLabel = new QLabel("-", summary);
    m_scopeValueLabel = new QLabel("-", summary);
    m_areaValueLabel = new QLabel("-", summary);
    summaryLayout->addRow("Status", m_statusValueLabel);
    summaryLayout->addRow("Adresa", m_addressValueLabel);
    summaryLayout->addRow("Scope", m_scopeValueLabel);
    summaryLayout->addRow("Area", m_areaValueLabel);
    m_titleLabel->hide();
    m_subtitleLabel->hide();
    summary->hide();

    auto *proposalTitle = new QLabel("Pracovni navrh nabidky", card);
    proposalTitle->setObjectName("subSectionTitle");
    auto *proposalCard = new QFrame(card);
    proposalCard->setObjectName("summaryCard");
    auto *proposalLayout = new QVBoxLayout(proposalCard);
    proposalLayout->setContentsMargins(16, 16, 16, 16);
    proposalLayout->setSpacing(12);

    auto *proposalSummaryCard = new QFrame(proposalCard);
    proposalSummaryCard->setObjectName("proposalInnerCard");
    auto *proposalSummaryLayout = new QFormLayout(proposalSummaryCard);
    proposalSummaryLayout->setContentsMargins(12, 12, 12, 12);
    m_proposalStatusValueLabel = new QLabel("-", proposalSummaryCard);
    m_referenceTestContextLabel = new QLabel(proposalSummaryCard);
    m_referenceTestContextLabel->setWordWrap(true);
    m_referenceTestContextLabel->hide();
    m_proposalSubjectEdit = new QLineEdit(proposalSummaryCard);
    m_proposalSummaryEdit = new QPlainTextEdit(proposalSummaryCard);
    m_proposalSummaryEdit->setMaximumHeight(80);
    m_proposalMaterialCostEdit = new QLineEdit(proposalSummaryCard);
    m_proposalLaborCostEdit = new QLineEdit(proposalSummaryCard);
    m_proposalAmortizationEdit = new QLineEdit(proposalSummaryCard);
    m_proposalMarginEdit = new QLineEdit(proposalSummaryCard);
    m_proposalTotalValueLabel = new QLabel("-", proposalSummaryCard);
    m_proposalSupplierEdit = new QLineEdit(proposalSummaryCard);
    m_proposalCompanyEdit = new QLineEdit(proposalSummaryCard);
    proposalSummaryLayout->addRow("Stav navrhu", m_proposalStatusValueLabel);
    proposalSummaryLayout->addRow("Test kontext", m_referenceTestContextLabel);
    proposalSummaryLayout->addRow("Predmet", m_proposalSubjectEdit);
    proposalSummaryLayout->addRow("Shrnuti", m_proposalSummaryEdit);
    proposalSummaryLayout->addRow("Cena materialu", m_proposalMaterialCostEdit);
    proposalSummaryLayout->addRow("Cena prace", m_proposalLaborCostEdit);
    proposalSummaryLayout->addRow("Amortizace", m_proposalAmortizationEdit);
    proposalSummaryLayout->addRow("Marze", m_proposalMarginEdit);
    proposalSummaryLayout->addRow("Celkem", m_proposalTotalValueLabel);
    proposalSummaryLayout->addRow("Dodavatel", m_proposalSupplierEdit);
    proposalSummaryLayout->addRow("Realizacni firma", m_proposalCompanyEdit);

    auto *proposalActionsLayout = new QHBoxLayout();
    proposalActionsLayout->setSpacing(10);
    m_saveProposalButton = new QPushButton("Save", proposalCard);
    m_saveProposalButton->setEnabled(false);
    m_createFinalProposalButton = new QPushButton("Vytvorit finalni verzi", proposalCard);
    m_createFinalProposalButton->setEnabled(false);
    proposalActionsLayout->addWidget(m_saveProposalButton);
    proposalActionsLayout->addWidget(m_createFinalProposalButton);
    proposalActionsLayout->addStretch();

    auto *proposalWorkItemsTitle = new QLabel("Navrzene kroky", proposalCard);
    proposalWorkItemsTitle->setObjectName("subSectionTitle");
    m_proposalWorkItemsList = new QListWidget(proposalCard);
    m_proposalWorkItemsList->setObjectName("detailList");
    m_proposalWorkItemsList->setMaximumHeight(140);

    auto *proposalMaterialsTitle = new QLabel("Navrzene materialy", proposalCard);
    proposalMaterialsTitle->setObjectName("subSectionTitle");
    m_proposalMaterialsList = new QListWidget(proposalCard);
    m_proposalMaterialsList->setObjectName("detailList");
    m_proposalMaterialsList->setMaximumHeight(150);

    auto *finalProposalTitle = new QLabel("Finalni verze", proposalCard);
    finalProposalTitle->setObjectName("subSectionTitle");
    auto *finalProposalCard = new QFrame(proposalCard);
    finalProposalCard->setObjectName("proposalInnerCard");
    finalProposalCard->setMinimumHeight(150);
    auto *finalProposalLayout = new QFormLayout(finalProposalCard);
    finalProposalLayout->setContentsMargins(12, 12, 12, 12);
    finalProposalLayout->setVerticalSpacing(10);
    m_finalProposalStatusValueLabel = new QLabel("zatim nevytvoreno", finalProposalCard);
    m_finalProposalVersionValueLabel = new QLabel("-", finalProposalCard);
    m_finalProposalSubjectValueLabel = new QLabel("-", finalProposalCard);
    m_finalProposalSubjectValueLabel->setWordWrap(true);
    m_finalProposalSummaryValueLabel = new QLabel("Po potvrzeni server vytvori finalni verzi a automaticky pripravi DOCX i PDF.", finalProposalCard);
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

    auto *caseActionsTitle = new QLabel("Zakladni akce", card);
    caseActionsTitle->setObjectName("subSectionTitle");
    auto *caseActionsLayout = new QHBoxLayout();
    caseActionsLayout->setSpacing(10);
    m_saveAsButton = new QPushButton("Save As", card);
    m_saveAsButton->setEnabled(false);
    m_newVariantButton = new QPushButton("Nova varianta", card);
    m_newVariantButton->setEnabled(false);
    m_sendCaseButton = new QPushButton("Odeslat zakazku", card);
    m_sendCaseButton->setEnabled(false);
    caseActionsLayout->addWidget(m_saveAsButton);
    caseActionsLayout->addWidget(m_newVariantButton);
    caseActionsLayout->addWidget(m_sendCaseButton);
    caseActionsLayout->addStretch();
    m_newVariantButton->setVisible(false);
    m_sendCaseButton->setVisible(false);

    auto *activityTitle = new QLabel("Next milestones", card);
    activityTitle->setObjectName("subSectionTitle");
    auto *activityList = new QListWidget(card);
    activityList->addItem("Photos tab s preview a overlay vrstvou");
    activityList->addItem("Findings tab s potvrzenim a opravou");
    activityList->addItem("Recommendations a jednoduchy report");
    activityList->setObjectName("detailList");

    auto *imagesTitle = new QLabel("Images panel", card);
    imagesTitle->setObjectName("subSectionTitle");
    m_primaryImageLabel = new QLabel("Vychozi fotka pro analyzu: -", card);
    m_primaryImageLabel->setObjectName("primaryImageLabel");
    m_primaryImagePreviewLabel = new QLabel("Preview hlavni fotky se zobrazi po nacteni case.", card);
    m_primaryImagePreviewLabel->setObjectName("primaryImagePreview");
    m_primaryImagePreviewLabel->setAlignment(Qt::AlignCenter);
    m_primaryImagePreviewLabel->setWordWrap(true);
    m_primaryImagePreviewLabel->setMinimumHeight(420);
    m_primaryImagePreviewLabel->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
    m_imageHintLabel = new QLabel("Po vyberu case se sem nactou obrazky a jejich metadata.", card);
    m_imageHintLabel->setObjectName("hintLabel");
    m_imageHintLabel->setWordWrap(true);
    auto *imageActionsLayout = new QHBoxLayout();
    imageActionsLayout->setSpacing(10);
    m_setPrimaryButton = new QPushButton("Nastavit jako hlavni", card);
    m_setPrimaryButton->setEnabled(false);
    m_setAnalysisReferenceButton = new QPushButton("Pouzit pro analyzu", card);
    m_setAnalysisReferenceButton->setEnabled(false);
    m_setPrimaryButton->setVisible(false);
    m_setAnalysisReferenceButton->setVisible(false);
    m_moveUpButton = new QPushButton(QStringLiteral("\u25C0"), card);
    m_moveUpButton->setEnabled(false);
    m_moveDownButton = new QPushButton(QStringLiteral("\u25B6"), card);
    m_moveDownButton->setEnabled(false);
    m_moveUpButton->setObjectName("imageNavButton");
    m_moveDownButton->setObjectName("imageNavButton");
    m_moveUpButton->setMinimumSize(40, 40);
    m_moveDownButton->setMinimumSize(40, 40);
    m_moveUpButton->setMaximumSize(40, 40);
    m_moveDownButton->setMaximumSize(40, 40);
    imageActionsLayout->addWidget(m_moveUpButton);
    imageActionsLayout->addWidget(m_moveDownButton);
    imageActionsLayout->addStretch();
    m_thumbnailScrollArea = new QScrollArea(card);
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

    cardLayout->addWidget(m_errorLabel);
    cardLayout->addWidget(imagesTitle);
    cardLayout->addWidget(m_primaryImageLabel);
    cardLayout->addWidget(m_primaryImagePreviewLabel);
    cardLayout->addWidget(m_imageHintLabel);
    cardLayout->addLayout(imageActionsLayout);
    cardLayout->addWidget(m_thumbnailScrollArea);
    cardLayout->addWidget(proposalTitle);
    cardLayout->addWidget(proposalCard);
    cardLayout->addWidget(caseActionsTitle);
    cardLayout->addLayout(caseActionsLayout);
    cardLayout->addWidget(activityTitle);
    cardLayout->addWidget(activityList, 1);

    layout->addWidget(card);

    setStyleSheet(R"(
        QFrame#detailCard {
            background: #fffaf2;
            border: 1px solid #eadcc8;
            border-radius: 18px;
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
        QLabel#primaryImagePreview {
            background: #f7efe4;
            border: 1px solid #eadcc8;
            border-radius: 14px;
            color: #607080;
            padding: 16px;
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
            border: 1px solid #d18841;
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
    connect(m_saveAsButton, &QPushButton::clicked, this, [this]() {
        duplicateCase("copy");
    });
    connect(m_newVariantButton, &QPushButton::clicked, this, [this]() {
        if (!m_caseId.isEmpty()) {
            emit newVariantRequested(m_caseId);
        }
    });
    connect(m_sendCaseButton, &QPushButton::clicked, this, [this]() {
        sendCurrentCase();
    });
    connect(m_saveProposalButton, &QPushButton::clicked, this, [this]() {
        saveProposalDraft();
    });
    connect(m_createFinalProposalButton, &QPushButton::clicked, this, [this]() {
        createFinalProposal();
    });
    m_imagePollingTimer = new QTimer(this);
    m_imagePollingTimer->setInterval(kImagePollingIntervalMs);
    connect(m_imagePollingTimer, &QTimer::timeout, this, [this]() {
        pollImageStatuses();
    });

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
    m_isReferenceDataset = caseDto.isReferenceDataset;
    m_expectedScope = caseDto.expectedScope;
    m_currentRepairScope = caseDto.repairScope;
    m_currentProposalWorkItems = caseDto.proposalWorkItems;
    m_currentProposalMaterials = caseDto.proposalMaterials;
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
    m_scopeValueLabel->setText(caseDto.repairScope.isEmpty() ? "-" : caseDto.repairScope);
    m_areaValueLabel->setText(caseDto.areaLabel.isEmpty() ? "-" : caseDto.areaLabel);
    m_proposalStatusValueLabel->setText(proposalStatusLabel(caseDto.proposalStatus));
    updateReferenceTestContextLabel();
    m_proposalSubjectEdit->setText(caseDto.proposalSubject);
    m_proposalSummaryEdit->setPlainText(caseDto.proposalSummary);
    m_proposalMaterialCostEdit->setText(formatDecimalForEdit(caseDto.proposalMaterialCostLabel));
    m_proposalLaborCostEdit->setText(formatDecimalForEdit(caseDto.proposalLaborCostLabel));
    m_proposalAmortizationEdit->setText(formatDecimalForEdit(caseDto.proposalAmortizationLabel));
    m_proposalMarginEdit->setText(formatDecimalForEdit(caseDto.proposalMarginLabel));
    m_proposalTotalValueLabel->setText(caseDto.proposalTotalPriceLabel.isEmpty() ? "-" : caseDto.proposalTotalPriceLabel);
    m_proposalSupplierEdit->setText(caseDto.proposalRecommendedSupplier);
    m_proposalCompanyEdit->setText(caseDto.proposalRecommendedCompany);
    m_finalProposalStatusValueLabel->setText(finalProposalStatusLabel(caseDto.finalProposalStatus));
    m_finalProposalVersionValueLabel->setText(caseDto.finalProposalDraftVersionLabel.isEmpty() ? "-" : caseDto.finalProposalDraftVersionLabel);
    m_finalProposalSubjectValueLabel->setText(caseDto.finalProposalSubject.isEmpty() ? "-" : caseDto.finalProposalSubject);
    m_finalProposalSummaryValueLabel->setText(
        caseDto.finalProposalSummary.isEmpty()
            ? "Zatim neni vytvorena finalni verze. Po potvrzeni server pripravi DOCX i PDF automaticky."
            : caseDto.finalProposalSummary);
    m_finalProposalTotalValueLabel->setText(
        caseDto.finalProposalTotalPriceLabel.isEmpty() ? "-" : caseDto.finalProposalTotalPriceLabel);
    m_proposalWorkItemsList->clear();
    if (caseDto.proposalWorkItems.isEmpty()) {
        m_proposalWorkItemsList->addItem("Navrh praci se doplni po zpracovani fotek.");
    } else {
        m_proposalWorkItemsList->addItems(caseDto.proposalWorkItems);
    }
    m_proposalMaterialsList->clear();
    if (caseDto.proposalMaterials.isEmpty()) {
        m_proposalMaterialsList->addItem("Navrh materialu se doplni po zpracovani fotek.");
    } else {
        m_proposalMaterialsList->addItems(caseDto.proposalMaterials);
    }
    if (m_saveProposalButton) {
        m_saveProposalButton->setEnabled(!caseDto.id.isEmpty());
    }
    if (m_createFinalProposalButton) {
        m_createFinalProposalButton->setEnabled(!caseDto.id.isEmpty());
    }
    if (m_saveAsButton) {
        m_saveAsButton->setEnabled(true);
    }
    if (m_newVariantButton) {
        m_newVariantButton->setEnabled(true);
    }
    if (m_sendCaseButton) {
        m_sendCaseButton->setEnabled(caseDto.status.compare("sent", Qt::CaseInsensitive) != 0
            && caseDto.status.compare("completed", Qt::CaseInsensitive) != 0);
    }
}

void CaseDetailView::clearCase()
{
    stopImageStatusPolling();
    m_caseId.clear();
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
    m_referenceTestContextLabel->clear();
    m_referenceTestContextLabel->hide();
    m_proposalSubjectEdit->clear();
    m_proposalSummaryEdit->setPlainText("Po nahrani fotek se tady ukaze prvni serverovy navrh k editaci.");
    m_proposalMaterialCostEdit->clear();
    m_proposalLaborCostEdit->clear();
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
        m_proposalWorkItemsList->clear();
        m_proposalWorkItemsList->addItem("Navrzene kroky se objevi po serverovem zpracovani fotek.");
    }
    if (m_proposalMaterialsList) {
        m_proposalMaterialsList->clear();
        m_proposalMaterialsList->addItem("Navrzene materialy se objevi po serverovem zpracovani fotek.");
    }

    if (m_saveAsButton) {
        m_saveAsButton->setEnabled(false);
    }
    if (m_newVariantButton) {
        m_newVariantButton->setEnabled(false);
    }
    if (m_sendCaseButton) {
        m_sendCaseButton->setEnabled(false);
    }
    if (m_saveProposalButton) {
        m_saveProposalButton->setEnabled(false);
    }
    if (m_createFinalProposalButton) {
        m_createFinalProposalButton->setEnabled(false);
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
        .amortization = readDoubleFromEdit(m_proposalAmortizationEdit),
        .margin = readDoubleFromEdit(m_proposalMarginEdit),
        .recommendedSupplier = m_proposalSupplierEdit ? m_proposalSupplierEdit->text().trimmed() : QString(),
        .recommendedCompany = m_proposalCompanyEdit ? m_proposalCompanyEdit->text().trimmed() : QString(),
    };

    QString errorMessage;
    const auto updatedCase = apiService.updateCaseProposalDraft(m_caseId, payload, &errorMessage);
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

    const auto confirmation = QMessageBox::question(
        this,
        "Vytvorit finalni verzi",
        "Ze soucasneho navrhu vznikne finalni verze a server k ni automaticky pripravi DOCX i PDF. Pokracovat?",
        QMessageBox::Yes | QMessageBox::No,
        QMessageBox::No);
    if (confirmation != QMessageBox::Yes) {
        return;
    }

    ApiService apiService;
    QString errorMessage;
    const auto updatedCase = apiService.createCaseFinalProposal(m_caseId, &errorMessage);
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
        setImageHintMessage(QString("Zkonvertovano %1 fotek pro dalsi odeslani.").arg(readyCount));
    } else {
        setImageHintMessage(
            QString("Zkonvertovano %1 z %2 fotek. Zbytek potrebuje kontrolu.")
                .arg(readyCount)
                .arg(m_preparedLocalImages.size()),
            readyCount == 0);
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

    if (m_convertImagesButton) {
        m_convertImagesButton->setEnabled(!m_pendingLocalImagePaths.isEmpty());
    }
    if (m_uploadImagesButton) {
        const bool hasReadyImages = std::any_of(
            m_preparedLocalImages.begin(),
            m_preparedLocalImages.end(),
            [](const LocalPreparedImage &image) { return image.state == LocalImageState::ReadyToUpload; });
        m_uploadImagesButton->setEnabled(hasReadyImages);
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

void CaseDetailView::setSelectedImageAsPrimary()
{
    const auto *image = selectedImage();
    if (!image || m_caseId.isEmpty()) {
        return;
    }

    ApiService apiService;
    CaseDetailViewModel viewModel;
    if (!viewModel.setPrimaryImage(m_caseId, image->id, apiService)) {
        setImageHintMessage(viewModel.imageErrorMessage(), true);
        return;
    }

    const auto images = viewModel.loadCaseImages(m_caseId, apiService);
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
        setImageHintMessage(viewModel.imageErrorMessage(), true);
        return;
    }

    const auto images = viewModel.loadCaseImages(m_caseId, apiService);
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
        const auto confirmation = QMessageBox::question(
            this,
            "Vytvorit kopii bez fotek?",
            "Aktualni zakazka zatim nema nactene zadne fotky. Pokud budes kopirovat z prazdne kopie, nova zakazka bude take bez fotek.\n\nPokracovat i tak?",
            QMessageBox::Yes | QMessageBox::No,
            QMessageBox::No);
        if (confirmation != QMessageBox::Yes) {
            return;
        }
    }

    ApiService apiService;
    QString errorMessage;
    const auto duplicatedCaseId = apiService.duplicateCase(m_caseId, mode, &errorMessage);
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

    const auto confirmation = QMessageBox::question(
        this,
        "Odeslat zakazku",
        QString(
            "Zakazka \"%1\" bude oznacena jako odeslana a presunuta do historie.\n\n"
            "Tuto akci ted pouzivame jako potvrzeni finalni verze. Pokracovat?")
            .arg(m_titleLabel->text().isEmpty() ? "Bez nazvu" : m_titleLabel->text()),
        QMessageBox::Yes | QMessageBox::No,
        QMessageBox::No);
    if (confirmation != QMessageBox::Yes) {
        return;
    }

    ApiService apiService;
    QString errorMessage;
    if (!apiService.sendCase(m_caseId, &errorMessage)) {
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
    updatePrimaryImagePreview();
}

void CaseDetailView::setPrimaryImagePlaceholder(const QString &message)
{
    m_primaryImagePixmap = QPixmap();
    m_primaryImagePreviewLabel->setPixmap(QPixmap());
    m_primaryImagePreviewLabel->setText(message);
}

void CaseDetailView::updatePrimaryImagePreview()
{
    if (!m_primaryImagePreviewLabel || m_primaryImagePixmap.isNull()) {
        return;
    }

    QSize targetSize = m_primaryImagePreviewLabel->size() - QSize(32, 32);
    if (targetSize.width() <= 0 || targetSize.height() <= 0) {
        targetSize = QSize(320, 240);
    }

    m_primaryImagePreviewLabel->setText(QString());
    m_primaryImagePreviewLabel->setPixmap(
        m_primaryImagePixmap.scaled(targetSize, Qt::KeepAspectRatio, Qt::SmoothTransformation));
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
