#include "caselistview.h"

#include <algorithm>

#include <QLabel>
#include <QPushButton>
#include <QVBoxLayout>

#include "services/sessionservice.h"
#include "viewmodels/caselistviewmodel.h"

namespace {
constexpr auto kCompletedCaseStatus = "completed";
constexpr auto kSentCaseStatus = "sent";
}

CaseListView::CaseListView(SessionService &session, QWidget *parent)
    : QWidget(parent)
    , m_viewModel(new CaseListViewModel(session, this))
{
    connect(m_viewModel, &CaseListViewModel::casesLoaded,
            this, &CaseListView::onCasesLoaded);
    connect(m_viewModel, &CaseListViewModel::errorOccurred,
            this, &CaseListView::onCaseLoadError);
    connect(m_viewModel, &CaseListViewModel::sessionExpiredDetected,
            this, &CaseListView::sessionExpired);
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

    // Mobile cases: single "Editovat zakázku" entry point — toggles field buttons
    m_editCaseButton = new QPushButton(QString::fromUtf8("Editovat zak\u00e1zku \u25bc"), optionsCard);
    m_editCaseButton->setObjectName("optionNavButton");
    m_editCaseButton->setWhatsThis(QString::fromUtf8(
        "Rozbal\u00ed nebo sbal\u00ed jednotliv\u00e1 editovateln\u00e1 pole zak\u00e1zky "
        "(p\u0159edm\u011bt, ceny, materi\u00e1ly...). Tla\u010d\u00edtko se zobrazuje u mobiln\u00edch zak\u00e1zek."));
    optionsLayout->addWidget(m_editCaseButton);
    m_editCaseButton->hide();

    // Desktop (PC) cases: individual field shortcuts
    const auto addField = [&](const QString &label, const QString &key, const QString &whatsThis = {}) {
        auto *btn = createOptionButton(label, key, optionsCard);
        if (!whatsThis.isEmpty()) btn->setWhatsThis(whatsThis);
        m_fieldButtons.append(btn);
        optionsLayout->addWidget(btn);
    };
    addField("Predmet zakazky", "subject",
        QString::fromUtf8("Otev\u0159e editaci p\u0159edm\u011btu zak\u00e1zky \u2014 co p\u0159esn\u011b se bude opravovat nebo \u010distit."));
    addField("Cena materialu", "material_cost",
        QString::fromUtf8("Otev\u0159e editaci ceny materi\u00e1lu v CZK. Zad\u00e1v\u00e1 se bez DPH."));
    addField("Cena prace", "labor_cost",
        QString::fromUtf8("Otev\u0159e editaci ceny pr\u00e1ce v CZK. Zad\u00e1v\u00e1 se bez DPH."));
    addField("Materialy", "materials",
        QString::fromUtf8("Otev\u0159e seznam navr\u017een\u00fdch materi\u00e1l\u016f pro tuto zak\u00e1zku."));
    addField("Amortizace", "amortization",
        QString::fromUtf8("Otev\u0159e editaci amortizace (opot\u0159eben\u00ed n\u00e1\u0159ad\u00ed a vybaven\u00ed) v CZK."));
    addField("Marze", "margin",
        QString::fromUtf8("Otev\u0159e editaci mar\u017ee v procentech. Bude p\u0159i\u010dtena k celkov\u00e9 cen\u011b."));
    addField("Dodavatele materialu", "material_suppliers",
        QString::fromUtf8("Otev\u0159e editaci navr\u017een\u00fdch dodavatel\u016f materi\u00e1lu."));

    // Toggle field buttons on click (mobile accordion)
    connect(m_editCaseButton, &QPushButton::clicked, this, [this]() {
        m_fieldButtonsExpanded = !m_fieldButtonsExpanded;
        for (auto *btn : m_fieldButtons) {
            if (btn) btn->setVisible(m_fieldButtonsExpanded);
        }
        m_editCaseButton->setText(m_fieldButtonsExpanded
            ? QString::fromUtf8("Editovat zak\u00e1zku \u25b2")
            : QString::fromUtf8("Editovat zak\u00e1zku \u25bc"));
    });

    // Always visible
    auto *uploadPhotosBtn = createOptionButton(QString::fromUtf8("P\u0159id\u00e1n\u00ed fotek"), "upload_photos", optionsCard);
    uploadPhotosBtn->setWhatsThis(QString::fromUtf8("Otev\u0159e z\u00e1lo\u017eku Fotky, kde m\u016f\u017eete nahr\u00e1t nebo spravovat fotografie zak\u00e1zky."));
    optionsLayout->addWidget(uploadPhotosBtn);

    auto *saveBtn = createOptionButton(QString::fromUtf8("Ulo\u017eit"), "save", optionsCard);
    saveBtn->setObjectName("optionSaveButton");
    saveBtn->setWhatsThis(QString::fromUtf8("Ulo\u017e\u00ed aktu\u00e1ln\u00ed rozepsan\u00fd n\u00e1vrh zak\u00e1zky na server."));
    optionsLayout->addWidget(saveBtn);
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
        QPushButton#optionSaveButton {
            background: #c97b3d;
            border: none;
            border-radius: 12px;
            padding: 12px;
            text-align: left;
            font-weight: 700;
            color: white;
        }
        QPushButton#optionSaveButton:hover {
            background: #b56a30;
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
    m_pendingPreferredCaseId = preferredCurrentCaseId;
    m_pendingEmitSignal = emitSignal;
    m_viewModel->loadCases();
}

void CaseListView::onCasesLoaded(std::vector<CaseDto> cases)
{
    m_errorLabel->hide();
    m_cases = std::move(cases);

    QString nextCurrentCaseId = m_pendingPreferredCaseId.isEmpty() ? m_currentCaseId : m_pendingPreferredCaseId;
    const auto preferredIt = std::find_if(m_cases.begin(), m_cases.end(), [&](const CaseDto &c) {
        return c.id == nextCurrentCaseId && isWorkCase(c);
    });

    if (preferredIt == m_cases.end()) {
        const auto firstWorkIt = std::find_if(m_cases.begin(), m_cases.end(), [this](const CaseDto &c) {
            return isWorkCase(c);
        });
        nextCurrentCaseId = firstWorkIt != m_cases.end() ? firstWorkIt->id : QString();
    }

    m_currentCaseId = nextCurrentCaseId;

    if (m_pendingEmitSignal) {
        emit caseSelected(m_currentCaseId);
    }
}

void CaseListView::onCaseLoadError(const QString &message)
{
    m_errorLabel->setText(message);
    m_errorLabel->show();
    m_cases.clear();
    m_currentCaseId.clear();
    if (m_pendingEmitSignal) {
        emit caseSelected(QString());
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
            // Reset accordion to collapsed state when switching cases
            m_fieldButtonsExpanded = false;
            m_editCaseButton->setText(QString::fromUtf8("Editovat zak\u00e1zku \u25bc"));
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
