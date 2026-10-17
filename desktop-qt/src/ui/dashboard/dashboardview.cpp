#include "dashboardview.h"
#include "network/casesapi.h"

#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QListWidget>
#include <QPushButton>
#include <QShowEvent>
#include <QVBoxLayout>

static QFrame *makeStatCard(const QString &title, QLabel **valueOut, QWidget *parent)
{
    auto *card = new QFrame(parent);
    card->setObjectName("statCard");
    auto *lay = new QVBoxLayout(card);
    lay->setContentsMargins(16, 14, 16, 14);
    lay->setSpacing(4);
    auto *titleLabel = new QLabel(title, card);
    titleLabel->setObjectName("statTitle");
    auto *valueLabel = new QLabel("...", card);
    valueLabel->setObjectName("statValue");
    lay->addWidget(titleLabel);
    lay->addWidget(valueLabel);
    *valueOut = valueLabel;
    return card;
}

DashboardView::DashboardView(QWidget *parent)
    : QWidget(parent)
{
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(16);

    auto *card = new QFrame(this);
    card->setObjectName("dashboardCard");
    auto *cardLayout = new QVBoxLayout(card);
    cardLayout->setContentsMargins(20, 20, 20, 20);
    cardLayout->setSpacing(16);

    auto *headerRow = new QHBoxLayout();
    auto *title = new QLabel("Prehled", card);
    title->setObjectName("sectionTitle");

    auto *newBtn = new QPushButton("+ Nova zakázka", card);
    newBtn->setObjectName("newCaseBtn");
    auto *loadBtn = new QPushButton("Nacist zakázky", card);
    loadBtn->setObjectName("loadCasesBtn");

    headerRow->addWidget(title);
    headerRow->addStretch();
    headerRow->addWidget(loadBtn);
    headerRow->addWidget(newBtn);
    connect(newBtn, &QPushButton::clicked, this, &DashboardView::newCaseRequested);
    connect(loadBtn, &QPushButton::clicked, this, &DashboardView::loadCasesRequested);
    cardLayout->addLayout(headerRow);

    auto *stats = new QGridLayout();
    stats->setHorizontalSpacing(12);
    stats->setVerticalSpacing(12);
    stats->addWidget(makeStatCard("Celkem zakázek",         &m_statTotal,     card), 0, 0);
    stats->addWidget(makeStatCard("Probiha analyza",        &m_statAnalyzing, card), 0, 1);
    stats->addWidget(makeStatCard("Pripraveno k odeslani",  &m_statReady,     card), 1, 0);
    stats->addWidget(makeStatCard("Odeslano",               &m_statSent,      card), 1, 1);
    cardLayout->addLayout(stats);

    auto *recentTitle = new QLabel("Posledni zakázky", card);
    recentTitle->setObjectName("sectionSubTitle");
    cardLayout->addWidget(recentTitle);

    m_recentList = new QListWidget(card);
    m_recentList->setObjectName("recentList");
    m_recentList->setMaximumHeight(200);
    m_recentList->setFocusPolicy(Qt::NoFocus);
    m_recentList->setSelectionMode(QAbstractItemView::NoSelection);
    cardLayout->addWidget(m_recentList);

    m_statusLabel = new QLabel(QString(), card);
    m_statusLabel->setObjectName("dashStatusLabel");
    cardLayout->addWidget(m_statusLabel);

    layout->addWidget(card);

    setStyleSheet(R"(
        QFrame#dashboardCard {
            background: #fffaf2;
            border: 1px solid #eadcc8;
            border-radius: 18px;
        }
        QLabel#sectionTitle {
            font-size: 20px;
            font-weight: 700;
            color: #1f2933;
        }
        QLabel#sectionSubTitle {
            font-size: 14px;
            font-weight: 600;
            color: #314252;
        }
        QFrame#statCard {
            background: #f7efe4;
            border: 1px solid #eadcc8;
            border-radius: 14px;
        }
        QLabel#statTitle {
            font-size: 12px;
            color: #6b7c8e;
        }
        QLabel#statValue {
            font-size: 24px;
            font-weight: 700;
            color: #314252;
        }
        QPushButton#newCaseBtn {
            background: #1f6bab;
            color: white;
            border: none;
            border-radius: 8px;
            padding: 6px 16px;
            font-weight: 600;
            text-align: center;
        }
        QPushButton#newCaseBtn:hover {
            background: #1a5a93;
        }
        QPushButton#loadCasesBtn {
            background: #f0e8da;
            color: #4a3820;
            border: 1px solid #d9c9b0;
            border-radius: 8px;
            padding: 6px 16px;
            font-weight: 600;
            text-align: center;
        }
        QPushButton#loadCasesBtn:hover {
            background: #e8d9c4;
        }
        QListWidget#recentList {
            border: 1px solid #eadcc8;
            border-radius: 8px;
            background: white;
        }
        QLabel#dashStatusLabel {
            font-size: 11px;
            color: #9aabbf;
        }
    )");
}

void DashboardView::showEvent(QShowEvent *event)
{
    QWidget::showEvent(event);
    loadStats();
}

void DashboardView::loadStats()
{
    if (m_statusLabel) m_statusLabel->setText("Nacitam...");
    if (m_recentList) m_recentList->clear();

    CasesApi api;
    QString errorMessage;
    const auto cases = api.fetchCases(&errorMessage);

    if (!errorMessage.isEmpty()) {
        if (m_statusLabel)
            m_statusLabel->setText(QString("Chyba pri nacitani: %1").arg(errorMessage));
        return;
    }

    int total     = 0;
    int analyzing = 0;
    int ready     = 0;
    int sent      = 0;

    constexpr int kRecentCount = 6;
    int shown = 0;

    for (const auto &c : cases) {
        if (c.status != "archived" && c.status != "cancelled") {
            ++total;
        }
        if (c.status == "analyzing")                                       ++analyzing;
        if (c.status == "proposal_ready" || c.status == "quote_ready")    ++ready;
        if (c.status == "sent")                                            ++sent;

        if (shown < kRecentCount && m_recentList) {
            const QString badge = [&]() -> QString {
                if (c.status == "draft")          return "Koncept";
                if (c.status == "intake")         return "Ceka na analyzu";
                if (c.status == "analyzing")      return "Analyzuje se";
                if (c.status == "proposal_ready") return "Navrh hotov";
                if (c.status == "quote_ready")    return "K odeslani";
                if (c.status == "sent")           return "Odeslano";
                return c.status;
            }();
            m_recentList->addItem(
                QString("%1  \xe2\x80\x94  %2").arg(c.title, badge));
            ++shown;
        }
    }

    if (m_statTotal)     m_statTotal->setText(QString::number(total));
    if (m_statAnalyzing) m_statAnalyzing->setText(QString::number(analyzing));
    if (m_statReady)     m_statReady->setText(QString::number(ready));
    if (m_statSent)      m_statSent->setText(QString::number(sent));

    const int all = static_cast<int>(cases.size());
    if (m_statusLabel) {
        m_statusLabel->setText(shown < all
            ? QString("Zobrazuji poslednich %1 z %2 zakázek").arg(shown).arg(all)
            : QString("Celkem %1 zakázek").arg(all));
    }
}
