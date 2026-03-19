#include "caselistview.h"

#include <algorithm>

#include <QLabel>
#include <QPushButton>
#include <QVBoxLayout>

#include "services/apiservice.h"
#include "viewmodels/caselistviewmodel.h"

namespace {
constexpr auto kCompletedCaseStatus = "completed";
constexpr auto kSentCaseStatus = "sent";
}

CaseListView::CaseListView(QWidget *parent)
    : QWidget(parent)
{
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(20, 20, 20, 20);
    layout->setSpacing(14);

    auto *title = new QLabel("Moznosti", this);
    title->setObjectName("sectionTitle");
    auto *hint = new QLabel("Vyber si cast aktualni zakazky, kterou chces upravovat nebo doplnit.", this);
    hint->setWordWrap(true);
    hint->setObjectName("hintLabel");

    m_errorLabel = new QLabel(this);
    m_errorLabel->setObjectName("errorLabel");
    m_errorLabel->setWordWrap(true);
    m_errorLabel->hide();

    auto *optionsCard = new QWidget(this);
    optionsCard->setObjectName("optionsCard");
    auto *optionsLayout = new QVBoxLayout(optionsCard);
    optionsLayout->setContentsMargins(14, 14, 14, 14);
    optionsLayout->setSpacing(10);

    optionsLayout->addWidget(createOptionButton("Predmet zakazky", "subject", optionsCard));
    optionsLayout->addWidget(createOptionButton("Cena materialu", "material_cost", optionsCard));
    optionsLayout->addWidget(createOptionButton("Cena prace", "labor_cost", optionsCard));
    optionsLayout->addWidget(createOptionButton("Materialy", "materials", optionsCard));
    optionsLayout->addWidget(createOptionButton("Amortizace", "amortization", optionsCard));
    optionsLayout->addWidget(createOptionButton("Marze", "margin", optionsCard));
    optionsLayout->addWidget(createOptionButton("Dodavatele materialu", "material_suppliers", optionsCard));
    optionsLayout->addStretch();

    layout->addWidget(title);
    layout->addWidget(hint);
    layout->addWidget(m_errorLabel);
    layout->addWidget(optionsCard, 1);

    setStyleSheet(R"(
        QLabel#sectionTitle {
            font-size: 22px;
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
        QWidget#optionsCard {
            background: #fffaf2;
            border: 1px solid #eadcc8;
            border-radius: 14px;
        }
        QPushButton#optionNavButton {
            background: #f7efe4;
            border: 1px solid #eadcc8;
            border-radius: 12px;
            padding: 12px;
            text-align: left;
            font-weight: 700;
            color: #314252;
        }
        QPushButton#optionNavButton:hover {
            background: #f4e3cf;
        }
    )");

    reloadCases(QString(), true);
}

QString CaseListView::currentCaseId() const
{
    return m_currentCaseId;
}

QString CaseListView::currentCaseTitle() const
{
    const auto caseIt = std::find_if(m_cases.begin(), m_cases.end(), [this](const CaseDto &caseDto) {
        return caseDto.id == m_currentCaseId;
    });
    if (caseIt == m_cases.end()) {
        return {};
    }

    return caseIt->isReferenceDataset ? QString("[TEST] %1").arg(caseIt->title) : caseIt->title;
}

bool CaseListView::currentCaseIsReferenceDataset() const
{
    const auto caseIt = std::find_if(m_cases.begin(), m_cases.end(), [this](const CaseDto &caseDto) {
        return caseDto.id == m_currentCaseId;
    });
    return caseIt != m_cases.end() && caseIt->isReferenceDataset;
}

void CaseListView::reloadCases(const QString &preferredCurrentCaseId, bool emitSignal)
{
    CaseListViewModel viewModel;
    ApiService apiService;
    const auto loadedCases = viewModel.loadCases(apiService);

    if (loadedCases.empty() && !viewModel.errorMessage().isEmpty()) {
        m_errorLabel->setText(viewModel.errorMessage());
        m_errorLabel->show();
        m_cases.clear();
        m_currentCaseId.clear();
        if (emitSignal) {
            emit caseSelected(QString());
        }
        return;
    }

    m_errorLabel->hide();
    m_cases = loadedCases;

    QString nextCurrentCaseId = preferredCurrentCaseId.isEmpty() ? m_currentCaseId : preferredCurrentCaseId;
    const auto preferredIt = std::find_if(m_cases.begin(), m_cases.end(), [this, &nextCurrentCaseId](const CaseDto &caseDto) {
        return caseDto.id == nextCurrentCaseId && isWorkCase(caseDto);
    });

    if (preferredIt == m_cases.end()) {
        const auto firstWorkIt = std::find_if(m_cases.begin(), m_cases.end(), [this](const CaseDto &caseDto) {
            return isWorkCase(caseDto);
        });
        nextCurrentCaseId = firstWorkIt != m_cases.end() ? firstWorkIt->id : QString();
    }

    m_currentCaseId = nextCurrentCaseId;

    if (emitSignal) {
        emit caseSelected(m_currentCaseId);
    }
}

void CaseListView::setCurrentCaseId(const QString &caseId, bool emitSignal)
{
    m_currentCaseId = caseId;
    if (emitSignal) {
        emit caseSelected(m_currentCaseId);
    }
}

QPushButton *CaseListView::createOptionButton(const QString &label, const QString &optionKey, QWidget *parent)
{
    auto *button = new QPushButton(label, parent);
    button->setObjectName("optionNavButton");
    connect(button, &QPushButton::clicked, this, [this, optionKey]() {
        emit optionRequested(optionKey);
    });
    return button;
}

bool CaseListView::isHistoryCase(const CaseDto &caseDto) const
{
    return caseDto.status.compare(kCompletedCaseStatus, Qt::CaseInsensitive) == 0
        || caseDto.status.compare(kSentCaseStatus, Qt::CaseInsensitive) == 0;
}

bool CaseListView::isWorkCase(const CaseDto &caseDto) const
{
    return !isHistoryCase(caseDto);
}
