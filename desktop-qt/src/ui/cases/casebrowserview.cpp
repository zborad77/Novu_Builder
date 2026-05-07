#include "casebrowserview.h"

#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QScrollArea>
#include <QSizePolicy>
#include <QVBoxLayout>
#include <QWidget>

#include "services/apiservice.h"

namespace {

QString localizedCaseStatus(const QString &status)
{
    if (status == "draft") {
        return QString::fromUtf8("Rozpracov\u00e1no");
    }
    if (status == "analysed") {
        return QString::fromUtf8("Analyzov\u00e1no");
    }
    if (status == "in_progress") {
        return QString::fromUtf8("Zpracov\u00e1v\u00e1 se");
    }
    if (status == "sent") {
        return QString::fromUtf8("Odesl\u00e1no z\u00e1kazn\u00edkovi");
    }
    if (status == "completed") {
        return QString::fromUtf8("Dokon\u010deno");
    }
    return status;
}

} // namespace

CaseBrowserView::CaseBrowserView(QWidget *parent)
    : QWidget(parent)
{
    auto *rootLayout = new QVBoxLayout(this);
    rootLayout->setContentsMargins(0, 0, 0, 0);
    rootLayout->setSpacing(0);

    auto *card = new QFrame(this);
    card->setObjectName("browserCard");
    auto *cardLayout = new QVBoxLayout(card);
    cardLayout->setContentsMargins(20, 16, 20, 20);
    cardLayout->setSpacing(8);

    m_titleLabel = new QLabel(QString::fromUtf8("Zak\u00e1zky"), card);
    m_titleLabel->setObjectName("browserTitle");

    m_subtitleLabel = new QLabel(QString(), card);
    m_subtitleLabel->setObjectName("browserSubtitle");
    m_subtitleLabel->setWordWrap(true);

    m_statusLabel = new QLabel(QString(), card);
    m_statusLabel->setObjectName("browserStatus");
    m_statusLabel->setWordWrap(true);
    m_statusLabel->hide();

    cardLayout->addWidget(m_titleLabel);
    cardLayout->addWidget(m_subtitleLabel);
    cardLayout->addWidget(m_statusLabel);

    // Scrollable cards area
    auto *scrollArea = new QScrollArea(card);
    scrollArea->setWidgetResizable(true);
    scrollArea->setFrameShape(QFrame::NoFrame);
    scrollArea->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);

    m_cardsContainer = new QWidget(scrollArea);
    m_cardsContainer->setObjectName("cardsContainer");
    m_cardsLayout = new QVBoxLayout(m_cardsContainer);
    m_cardsLayout->setContentsMargins(0, 8, 0, 8);
    m_cardsLayout->setSpacing(10);
    m_cardsLayout->addStretch();

    scrollArea->setWidget(m_cardsContainer);
    cardLayout->addWidget(scrollArea, 1);

    rootLayout->addWidget(card);

    setStyleSheet(R"(
        QFrame#browserCard {
            background: #fffaf2;
            border: 1px solid #eadcc8;
            border-radius: 18px;
        }
        QLabel#browserTitle {
            font-size: 24px;
            font-weight: 700;
            color: #1f2933;
        }
        QLabel#browserSubtitle {
            color: #607080;
            font-size: 14px;
        }
        QLabel#browserStatus {
            color: #607080;
            font-size: 14px;
        }
        QPushButton#caseCard {
            background: #f7efe4;
            border: 1px solid #eadcc8;
            border-radius: 12px;
            padding: 10px 14px;
            text-align: left;
            min-height: 70px;
        }
        QPushButton#caseCard:hover {
            background: #f0e4d0;
            border-color: #d4b896;
        }
        QPushButton#caseCard:pressed {
            background: #e8d8c0;
        }
        QLabel#caseCardTitle {
            font-size: 14px;
            font-weight: 700;
            color: #1f2933;
        }
        QLabel#caseCardInfo {
            font-size: 12px;
            color: #607080;
        }
        QLabel#caseCardAuthor {
            font-size: 11px;
            color: #9a7a50;
            font-style: italic;
        }
        QLabel#sourceBadgeMobile {
            font-size: 11px;
            color: #1a6eb5;
            background: #ddeeff;
            border-radius: 6px;
            padding: 1px 6px;
        }
        QLabel#sourceBadgeDesktop {
            font-size: 11px;
            color: #2e6b3e;
            background: #d6f0dd;
            border-radius: 6px;
            padding: 1px 6px;
        }
        QWidget#cardsContainer {
            background: #fffaf2;
        }
    )");
}

void CaseBrowserView::loadCases(Mode mode)
{
    m_statusLabel->hide();

    if (mode == Mode::WorkCases) {
        m_titleLabel->setText(QString::fromUtf8("Rozpracovan\u00e9 zak\u00e1zky"));
        m_subtitleLabel->setText(
            QString::fromUtf8("Zak\u00e1zky, na kter\u00fdch se pracuje."));
    } else {
        m_titleLabel->setText(QString::fromUtf8("Historie zak\u00e1zek"));
        m_subtitleLabel->setText(
            QString::fromUtf8("Dokon\u010den\u00e9 a odeslan\u00e9 zak\u00e1zky."));
    }

    ApiService api;
    QString errorMessage;
    const auto allCases = api.fetchCases(&errorMessage);

    if (ApiService::sessionExpired()) {
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
        if (mode == Mode::WorkCases && !isClosed) {
            filtered.push_back(c);
        } else if (mode == Mode::HistoryCases && isClosed) {
            filtered.push_back(c);
        }
    }

    buildCards(filtered, mode);
}

void CaseBrowserView::buildCards(const std::vector<CaseDto> &cases, Mode mode)
{
    // Remove all widgets from cardsLayout except the trailing stretch
    while (m_cardsLayout->count() > 1) {
        auto *item = m_cardsLayout->takeAt(0);
        if (item->widget()) {
            item->widget()->deleteLater();
        }
        delete item;
    }

    if (cases.empty()) {
        m_statusLabel->setText(QString::fromUtf8("\u017d\u00e1dn\u00e9 zak\u00e1zky k zobrazen\u00ed."));
        m_statusLabel->show();
        return;
    }

    m_statusLabel->hide();

    const bool readOnly = (mode == Mode::HistoryCases);

    for (const auto &caseDto : cases) {
        auto *card = new QPushButton(m_cardsContainer);
        card->setObjectName("caseCard");
        card->setFlat(false);
        card->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

        auto *cardInnerLayout = new QVBoxLayout(card);
        cardInnerLayout->setContentsMargins(8, 8, 8, 8);
        cardInnerLayout->setSpacing(4);

        // Title row: name + source badge
        auto *titleRow = new QWidget(card);
        titleRow->setAttribute(Qt::WA_TransparentForMouseEvents);
        auto *titleRowLayout = new QHBoxLayout(titleRow);
        titleRowLayout->setContentsMargins(0, 0, 0, 0);
        titleRowLayout->setSpacing(8);

        auto *titleLbl = new QLabel(caseDto.title.isEmpty()
            ? QString::fromUtf8("(bez n\u00e1zvu)")
            : caseDto.title, titleRow);
        titleLbl->setObjectName("caseCardTitle");
        titleLbl->setAttribute(Qt::WA_TransparentForMouseEvents);

        const bool isMobile = (caseDto.source == QLatin1String("mobile"));
        const QString badgeText = isMobile
            ? QString::fromUtf8("Mobil")
            : QString::fromUtf8("PC");
        auto *sourceBadge = new QLabel(badgeText, titleRow);
        sourceBadge->setObjectName(isMobile ? "sourceBadgeMobile" : "sourceBadgeDesktop");
        sourceBadge->setAttribute(Qt::WA_TransparentForMouseEvents);

        titleRowLayout->addWidget(titleLbl);
        titleRowLayout->addWidget(sourceBadge);
        titleRowLayout->addStretch();

        const QString statusText = localizedCaseStatus(caseDto.status);
        const QString infoText = caseDto.addressLabel.isEmpty()
            ? statusText
            : (caseDto.addressLabel + " | " + statusText);
        auto *infoLbl = new QLabel(infoText, card);
        infoLbl->setObjectName("caseCardInfo");
        infoLbl->setAttribute(Qt::WA_TransparentForMouseEvents);

        cardInnerLayout->addWidget(titleRow);
        cardInnerLayout->addWidget(infoLbl);

        if (!caseDto.createdByName.isEmpty()) {
            auto *authorLbl = new QLabel(QString::fromUtf8("Technik: ") + caseDto.createdByName, card);
            authorLbl->setObjectName("caseCardAuthor");
            authorLbl->setAttribute(Qt::WA_TransparentForMouseEvents);
            cardInnerLayout->addWidget(authorLbl);
        }

        const QString caseId = caseDto.id;
        connect(card, &QPushButton::clicked, this, [this, caseId, readOnly]() {
            emit caseOpenRequested(caseId, readOnly);
        });

        // Insert before the trailing stretch (last item)
        m_cardsLayout->insertWidget(m_cardsLayout->count() - 1, card);
    }
}
