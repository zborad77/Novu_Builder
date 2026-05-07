#include "dashboardview.h"

#include <QFrame>
#include <QGridLayout>
#include <QLabel>
#include <QVBoxLayout>

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

    auto *title = new QLabel("Dashboard overview", card);
    title->setObjectName("sectionTitle");
    cardLayout->addWidget(title);

    auto *stats = new QGridLayout();
    stats->setHorizontalSpacing(12);
    stats->setVerticalSpacing(12);

    const QStringList labels = {
        "Active cases\n12",
        "Pending findings\n4",
        "Waiting analysis\n2",
        "Ready reports\n3"
    };

    for (int i = 0; i < labels.size(); ++i) {
        auto *statCard = new QFrame(card);
        statCard->setObjectName("statCard");
        auto *statLayout = new QVBoxLayout(statCard);
        statLayout->setContentsMargins(16, 16, 16, 16);
        auto *label = new QLabel(labels.at(i), statCard);
        label->setWordWrap(true);
        label->setObjectName("statLabel");
        statLayout->addWidget(label);
        stats->addWidget(statCard, i / 2, i % 2);
    }

    cardLayout->addLayout(stats);
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
        QFrame#statCard {
            background: #f7efe4;
            border: 1px solid #eadcc8;
            border-radius: 14px;
        }
        QLabel#statLabel {
            font-size: 16px;
            font-weight: 600;
            color: #314252;
        }
    )");
}
