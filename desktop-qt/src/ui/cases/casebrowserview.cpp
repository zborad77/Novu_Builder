#include "casebrowserview.h"

#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QScrollArea>
#include <QSizePolicy>
#include <QVBoxLayout>
#include <QWidget>

#include "network/casesapi.h"

namespace {

QString localizedCaseStatus(const QString &status)
{
    if (status == "draft")       return QString::fromUtf8("Rozpracov\u00e1no");
    if (status == "analysed")    return QString::fromUtf8("Analyzov\u00e1no");
    if (status == "in_progress") return QString::fromUtf8("Zpracov\u00e1v\u00e1 se");
    if (status == "sent")        return QString::fromUtf8("Odesl\u00e1no z\u00e1kazn\u00edkovi");
    if (status == "completed")   return QString::fromUtf8("Dokon\u010deno");
    return status;
}

QString statusColor(const QString &status)
{
    if (status == "in_progress") return "#c97b3d";
    if (status == "analysed")    return "#3a7bd5";
    if (status == "sent" || status == "completed") return "#2a9654";
    return "#94a3b4"; // draft / unknown
}

} // namespace

CaseBrowserView::CaseBrowserView(QWidget *parent)
    : QWidget(parent)
{
    auto *rootLayout = new QVBoxLayout(this);
    rootLayout->setContentsMargins(0, 0, 0, 0);
    rootLayout->setSpacing(10);

    // \u2500\u2500 Header \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    m_titleLabel = new QLabel(QString::fromUtf8("Zak\u00e1zky"), this);
    m_titleLabel->setObjectName("browserTitle");

    m_subtitleLabel = new QLabel(QString(), this);
    m_subtitleLabel->setObjectName("browserSubtitle");
    m_subtitleLabel->hide();

    m_statusLabel = new QLabel(QString(), this);
    m_statusLabel->setObjectName("browserStatus");
    m_statusLabel->setWordWrap(true);
    m_statusLabel->hide();

    // \u2500\u2500 Row list \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    auto *listFrame = new QFrame(this);
    listFrame->setObjectName("listFrame");
    auto *listFrameLayout = new QVBoxLayout(listFrame);
    listFrameLayout->setContentsMargins(0, 0, 0, 0);
    listFrameLayout->setSpacing(0);

    auto *scrollArea = new QScrollArea(listFrame);
    scrollArea->setWidgetResizable(true);
    scrollArea->setFrameShape(QFrame::NoFrame);
    scrollArea->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);

    m_cardsContainer = new QWidget(scrollArea);
    m_cardsContainer->setObjectName("cardsContainer");
    m_cardsLayout = new QVBoxLayout(m_cardsContainer);
    m_cardsLayout->setContentsMargins(0, 0, 0, 0);
    m_cardsLayout->setSpacing(0);
    m_cardsLayout->addStretch();

    scrollArea->setWidget(m_cardsContainer);
    listFrameLayout->addWidget(scrollArea);

    rootLayout->addWidget(m_titleLabel);
    rootLayout->addWidget(m_subtitleLabel);
    rootLayout->addWidget(m_statusLabel);
    rootLayout->addWidget(listFrame, 1);

    setStyleSheet(R"(
        QLabel#browserTitle {
            font-size: 20px;
            font-weight: 700;
            color: #1a2330;
        }
        QLabel#browserSubtitle {
            font-size: 12px;
            color: #7a8a9a;
        }
        QLabel#browserStatus {
            font-size: 13px;
            color: #516070;
            padding: 8px 12px;
            background: #fdecea;
            border-radius: 8px;
        }
        QFrame#listFrame {
            border: 1px solid #ded4c2;
            border-radius: 12px;
            background: #fffdf8;
        }
        QWidget#cardsContainer {
            background: transparent;
        }
        QPushButton#caseRow {
            background: transparent;
            border: none;
            border-bottom: 1px solid #ede5d6;
            border-radius: 0px;
            text-align: left;
            padding: 0px;
        }
        QPushButton#caseRow:hover {
            background: #f5ead8;
        }
        QPushButton#caseRow:pressed {
            background: #ede0c6;
        }
        QLabel#rowTitle {
            font-size: 13px;
            font-weight: 700;
            color: #1a2330;
        }
        QLabel#rowInfo {
            font-size: 12px;
            color: #516070;
        }
        QLabel#rowAuthor {
            font-size: 11px;
            color: #8a9aaa;
            font-style: italic;
        }
        QLabel#sourceBadgeMobile {
            font-size: 10px;
            color: #1a6eb5;
            background: #ddeeff;
            border-radius: 4px;
            padding: 1px 5px;
        }
        QLabel#sourceBadgeDesktop {
            font-size: 10px;
            color: #2e6b3e;
            background: #d6f0dd;
            border-radius: 4px;
            padding: 1px 5px;
        }
    )");
}

void CaseBrowserView::loadCases(Mode mode)
{
    m_statusLabel->hide();
    m_subtitleLabel->hide();

    m_titleLabel->setText(mode == Mode::WorkCases
        ? QString::fromUtf8("Rozpracovan\u00e9 zak\u00e1zky")
        : QString::fromUtf8("Historie zak\u00e1zek"));

    CasesApi api;
    QString errorMessage;
    const auto allCases = api.fetchCases(&errorMessage);

    if (CasesApi::sessionExpired()) {
        emit sessionExpired();
        return;
    }

    if (allCases.empty() && !errorMessage.isEmpty()) {
        m_statusLabel->setText(errorMessage);
        m_statusLabel->show();
        buildCards({}, mode);
        return;
    }

    std::vector<CaseDto> filtered;
    for (const auto &c : allCases) {
        const bool isClosed = (c.status == "sent" || c.status == "completed");
        if (mode == Mode::WorkCases && !isClosed)    filtered.push_back(c);
        else if (mode == Mode::HistoryCases && isClosed) filtered.push_back(c);
    }

    buildCards(filtered, mode);
}

void CaseBrowserView::buildCards(const std::vector<CaseDto> &cases, Mode mode)
{
    while (m_cardsLayout->count() > 1) {
        auto *item = m_cardsLayout->takeAt(0);
        if (item->widget()) item->widget()->deleteLater();
        delete item;
    }

    if (cases.empty()) {
        m_subtitleLabel->setText(QString::fromUtf8("0 zak\u00e1zek"));
        m_subtitleLabel->show();
        m_statusLabel->setText(QString::fromUtf8("\u017d\u00e1dn\u00e9 zak\u00e1zky k zobrazen\u00ed."));
        m_statusLabel->show();
        return;
    }

    m_statusLabel->hide();
    m_subtitleLabel->setText(QString::fromUtf8("%1 zak\u00e1zek").arg(cases.size()));
    m_subtitleLabel->show();

    const bool readOnly = (mode == Mode::HistoryCases);

    for (const auto &caseDto : cases) {
        auto *row = new QPushButton(m_cardsContainer);
        row->setObjectName("caseRow");
        row->setFlat(false);
        row->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

        auto *rowLayout = new QHBoxLayout(row);
        rowLayout->setContentsMargins(0, 0, 0, 0);
        rowLayout->setSpacing(0);

        // Status color strip (4px left bar)
        auto *strip = new QFrame(row);
        strip->setFixedWidth(4);
        strip->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Expanding);
        strip->setMinimumHeight(24);
        strip->setStyleSheet(
            QString("background: %1; border-radius: 0px;").arg(statusColor(caseDto.status)));
        strip->setAttribute(Qt::WA_TransparentForMouseEvents);

        // Content
        auto *content = new QWidget(row);
        content->setAttribute(Qt::WA_TransparentForMouseEvents);
        auto *contentLayout = new QVBoxLayout(content);
        contentLayout->setContentsMargins(12, 9, 12, 9);
        contentLayout->setSpacing(2);

        // Title row: name + source badge
        auto *titleRow = new QWidget(content);
        titleRow->setAttribute(Qt::WA_TransparentForMouseEvents);
        auto *titleRowLayout = new QHBoxLayout(titleRow);
        titleRowLayout->setContentsMargins(0, 0, 0, 0);
        titleRowLayout->setSpacing(6);

        auto *titleLbl = new QLabel(
            caseDto.title.isEmpty()
                ? QString::fromUtf8("(bez n\u00e1zvu)")
                : caseDto.title,
            titleRow);
        titleLbl->setObjectName("rowTitle");
        titleLbl->setAttribute(Qt::WA_TransparentForMouseEvents);

        const bool isMobile = (caseDto.source == QLatin1String("mobile"));
        auto *sourceBadge = new QLabel(isMobile ? "Mobil" : "PC", titleRow);
        sourceBadge->setObjectName(isMobile ? "sourceBadgeMobile" : "sourceBadgeDesktop");
        sourceBadge->setAttribute(Qt::WA_TransparentForMouseEvents);

        titleRowLayout->addWidget(titleLbl, 1);
        titleRowLayout->addWidget(sourceBadge, 0, Qt::AlignVCenter);
        contentLayout->addWidget(titleRow);

        // Info: address \u00b7 status
        const QString statusText = localizedCaseStatus(caseDto.status);
        const QString infoText = caseDto.addressLabel.isEmpty()
            ? statusText
            : caseDto.addressLabel + QString::fromUtf8(" \u00b7 ") + statusText;
        auto *infoLbl = new QLabel(infoText, content);
        infoLbl->setObjectName("rowInfo");
        infoLbl->setAttribute(Qt::WA_TransparentForMouseEvents);
        contentLayout->addWidget(infoLbl);

        if (!caseDto.createdByName.isEmpty()) {
            auto *authorLbl = new QLabel(
                QString::fromUtf8("Technik: ") + caseDto.createdByName, content);
            authorLbl->setObjectName("rowAuthor");
            authorLbl->setAttribute(Qt::WA_TransparentForMouseEvents);
            contentLayout->addWidget(authorLbl);
        }

        rowLayout->addWidget(strip, 0);
        rowLayout->addWidget(content, 1);

        const QString caseId = caseDto.id;
        connect(row, &QPushButton::clicked, this, [this, caseId, readOnly]() {
            emit caseOpenRequested(caseId, readOnly);
        });

        m_cardsLayout->insertWidget(m_cardsLayout->count() - 1, row);
    }
}
