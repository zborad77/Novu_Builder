#include "caselistview.h"

#include <algorithm>

#include <QLabel>
#include <QPushButton>
#include <QVBoxLayout>

#include "network/casesapi.h"
#include "viewmodels/caselistviewmodel.h"

namespace {
constexpr auto kCompletedCaseStatus = "completed";
constexpr auto kSentCaseStatus = "sent";
}

CaseListView::CaseListView(QWidget *parent)
    : QWidget(parent)
{
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(12, 12, 12, 12);
    layout->setSpacing(4);

    auto *title = new QLabel(QString::fromUtf8("AKCE"), this);
    title->setObjectName("panelSectionLabel");
    layout->addWidget(title);

    m_errorLabel = new QLabel(this);
    m_errorLabel->setObjectName("errorLabel");
    m_errorLabel->setWordWrap(true);
    m_errorLabel->hide();
    layout->addWidget(m_errorLabel);

    // Mobile: single "Editovat zakázku" toggle
    m_editCaseButton = new QPushButton(QString::fromUtf8("Editovat zakázku ▼"), this);
    m_editCaseButton->setObjectName("optionNavButton");
    m_editCaseButton->setWhatsThis(QString::fromUtf8(
        "Rozbalí nebo sbalí jednotlivá editovatelná pole zakázky "
        "(předmět, ceny, materiály...). Tlačítko se zobrazuje u mobilních zakázek."));
    layout->addWidget(m_editCaseButton);
    m_editCaseButton->hide();

    // Desktop: field shortcuts (always visible for desktop cases)
    const auto addField = [&](const QString &label, const QString &key, const QString &whatsThis = {}) {
        auto *btn = createOptionButton(label, key, this);
        if (!whatsThis.isEmpty()) btn->setWhatsThis(whatsThis);
        m_fieldButtons.append(btn);
        layout->addWidget(btn);
    };
    addField(QString::fromUtf8("Předmět zakázky"), "subject",
        QString::fromUtf8("Otevře editaci předmětu zakázky — co přesně se bude opravovat nebo čistit."));
    addField(QString::fromUtf8("Cena materiálu"), "material_cost",
        QString::fromUtf8("Otevře editaci ceny materiálu v CZK. Zadává se bez DPH."));
    addField(QString::fromUtf8("Cena práce"), "labor_cost",
        QString::fromUtf8("Otevře editaci ceny práce v CZK. Zadává se bez DPH."));
    addField(QString::fromUtf8("Materiály"), "materials",
        QString::fromUtf8("Otevře seznam navržených materiálů pro tuto zakázku."));
    addField("Amortizace", "amortization",
        QString::fromUtf8("Otevře editaci amortizace (opotřebení nářadí a vybavení) v CZK."));
    addField(QString::fromUtf8("Marže"), "margin",
        QString::fromUtf8("Otevře editaci marže v procentech. Bude přičtena k celkové ceně."));
    addField(QString::fromUtf8("Dodavatelé materiálu"), "material_suppliers",
        QString::fromUtf8("Otevře editaci navržených dodavatelů materiálu."));

    connect(m_editCaseButton, &QPushButton::clicked, this, [this]() {
        m_fieldButtonsExpanded = !m_fieldButtonsExpanded;
        for (auto *btn : m_fieldButtons) {
            if (btn) btn->setVisible(m_fieldButtonsExpanded);
        }
        m_editCaseButton->setText(m_fieldButtonsExpanded
            ? QString::fromUtf8("Editovat zakázku ▲")
            : QString::fromUtf8("Editovat zakázku ▼"));
    });

    auto *uploadPhotosBtn = createOptionButton(
        QString::fromUtf8("Přidání fotek"), "upload_photos", this);
    uploadPhotosBtn->setWhatsThis(QString::fromUtf8(
        "Otevře záložku Fotky, kde můžete nahrát nebo spravovat fotografie zakázky."));
    layout->addWidget(uploadPhotosBtn);

    layout->addStretch();

    auto *saveBtn = createOptionButton(
        QString::fromUtf8("Uložit"), "save", this);
    saveBtn->setObjectName("optionSaveButton");
    saveBtn->setWhatsThis(QString::fromUtf8(
        "Uloží aktuální rozepsaný návrh zakázky na server."));
    layout->addWidget(saveBtn);

    setStyleSheet(R"(
        QLabel#panelSectionLabel {
            font-size: 11px;
            font-weight: 700;
            color: #94a3b4;
            letter-spacing: 1px;
            padding-bottom: 2px;
        }
        QLabel#errorLabel {
            color: #a3341d;
            font-weight: 600;
            font-size: 13px;
        }
        QPushButton#optionNavButton {
            background: transparent;
            border: none;
            border-radius: 8px;
            padding: 7px 10px;
            text-align: left;
            font-weight: 600;
            color: #374858;
            font-size: 13px;
        }
        QPushButton#optionNavButton:hover {
            background: #ede4d4;
        }
        QPushButton#optionSaveButton {
            background: #c97b3d;
            border: none;
            border-radius: 10px;
            padding: 10px 12px;
            text-align: center;
            font-weight: 700;
            color: white;
            font-size: 13px;
        }
        QPushButton#optionSaveButton:hover {
            background: #b56a30;
        }
        QPushButton#optionSaveButton:disabled {
            background: #d4a57a;
            color: #f5e8d8;
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
    CasesApi apiService;
    const auto loadedCases = viewModel.loadCases(apiService);

    if (CasesApi::sessionExpired()) {
        emit sessionExpired();
        return;
    }

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

void CaseListView::updateForCaseSource(const QString &source)
{
    const bool isDesktop = (source == QStringLiteral("desktop"));
    if (m_editCaseButton) {
        m_editCaseButton->setVisible(!isDesktop);
        if (!isDesktop) {
            m_fieldButtonsExpanded = false;
            m_editCaseButton->setText(QString::fromUtf8("Editovat zakázku ▼"));
        }
    }
    for (auto *btn : m_fieldButtons) {
        if (btn) btn->setVisible(isDesktop || m_fieldButtonsExpanded);
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
