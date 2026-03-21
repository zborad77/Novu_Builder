#include "newcaseview.h"

#include <QBuffer>
#include <QComboBox>
#include <QFileDialog>
#include <QFileInfo>
#include <QFormLayout>
#include <QFrame>
#include <QHBoxLayout>
#include <QImage>
#include <QImageReader>
#include <QImageWriter>
#include <QLabel>
#include <QLineEdit>
#include <QMessageBox>
#include <QPixmap>
#include <QPushButton>
#include <QScrollArea>
#include <QSizePolicy>
#include <QVBoxLayout>

#include "services/apiservice.h"

namespace {
constexpr int kThumbSize = 96;
constexpr int kPreparedMaxEdge = 1600;
constexpr int kPreparedQuality = 85;

UploadImageDto prepareImage(const QString &path)
{
    QImageReader reader(path);
    reader.setAutoTransform(true);
    QImage img = reader.read();
    if (img.isNull()) return {};

    if (img.width() > kPreparedMaxEdge || img.height() > kPreparedMaxEdge) {
        img = img.scaled(kPreparedMaxEdge, kPreparedMaxEdge, Qt::KeepAspectRatio, Qt::SmoothTransformation);
    }

    QByteArray payload;
    QBuffer buf(&payload);
    buf.open(QIODevice::WriteOnly);
    QImageWriter writer(&buf, "JPEG");
    writer.setQuality(kPreparedQuality);
    writer.write(img);

    const QString filename = QFileInfo(path).completeBaseName() + ".jpg";
    return UploadImageDto{.originalFilename = filename, .mimeType = "image/jpeg", .payload = payload};
}
} // namespace

NewCaseView::NewCaseView(QWidget *parent)
    : QWidget(parent)
{
    auto *rootLayout = new QVBoxLayout(this);
    rootLayout->setContentsMargins(0, 0, 0, 0);
    rootLayout->setSpacing(0);

    auto *scroll = new QScrollArea(this);
    scroll->setWidgetResizable(true);
    scroll->setFrameShape(QFrame::NoFrame);

    auto *page = new QWidget();
    auto *pageLayout = new QVBoxLayout(page);
    pageLayout->setContentsMargins(24, 24, 24, 24);
    pageLayout->setSpacing(18);
    scroll->setWidget(page);
    rootLayout->addWidget(scroll, 1);

    // ── Header row ────────────────────────────────────────────────────────────
    auto *headerRow = new QHBoxLayout();
    auto *backButton = new QPushButton(QString::fromUtf8("← Zp\u011bt"));
    backButton->setObjectName("secondaryButton");
    m_submitButton = new QPushButton(QString::fromUtf8("Odeslat k anal\u00fdze AI"));
    m_submitButton->setObjectName("primaryButton");
    m_submitButton->setEnabled(false);
    headerRow->addWidget(backButton);
    headerRow->addStretch();
    headerRow->addWidget(m_submitButton);
    pageLayout->addLayout(headerRow);

    // ── Title ─────────────────────────────────────────────────────────────────
    auto *titleLabel = new QLabel(QString::fromUtf8("Nov\u00e1 zak\u00e1zka z PC"));
    titleLabel->setObjectName("sectionTitle");
    auto *hintLabel = new QLabel(
        QString::fromUtf8("Vypl\u0148te \u00fadaje, vyberte fotografie a ode\u0161lete k anal\u00fdze."));
    hintLabel->setObjectName("hintLabel");
    hintLabel->setWordWrap(true);
    pageLayout->addWidget(titleLabel);
    pageLayout->addWidget(hintLabel);

    // ── Form card ─────────────────────────────────────────────────────────────
    auto *formCard = new QFrame();
    formCard->setObjectName("detailCard");
    auto *formLayout = new QFormLayout(formCard);
    formLayout->setContentsMargins(16, 16, 16, 16);
    formLayout->setSpacing(10);
    formLayout->setLabelAlignment(Qt::AlignRight | Qt::AlignVCenter);

    m_titleEdit = new QLineEdit();
    m_titleEdit->setPlaceholderText(QString::fromUtf8("Naz\u0435v zak\u00e1zky (povinn\u00e9)"));
    m_addressEdit = new QLineEdit();
    m_addressEdit->setPlaceholderText(QString::fromUtf8("Adresa objektu"));
    m_repairScopeCombo = new QComboBox();
    m_repairScopeCombo->addItem(QString::fromUtf8("Lok\u00e1ln\u00ed oprava"), "local_repair");
    m_repairScopeCombo->addItem(QString::fromUtf8("Cel\u00fd n\u00e1t\u011br"), "full_repaint");
    m_repairScopeCombo->addItem(QString::fromUtf8("Strukturaln\u00ed oprava"), "structural_repair");
    m_repairScopeCombo->addItem(QString::fromUtf8("\u010ci\u0161t\u011bn\u00ed"), "cleaning");
    m_repairScopeCombo->addItem(QString::fromUtf8("Jin\u00e9"), "other");
    m_descriptionEdit = new QLineEdit();
    m_descriptionEdit->setPlaceholderText(QString::fromUtf8("Kr\u00e1tk\u00fd popis pro AI (nap\u0159. \"Zne\u010di\u0161t\u011bn\u00e1 severn\u00ed st\u011bna\")"));

    formLayout->addRow(QString::fromUtf8("N\u00e1zev:"), m_titleEdit);
    formLayout->addRow(QString::fromUtf8("Adresa:"), m_addressEdit);
    formLayout->addRow(QString::fromUtf8("Typ opravy:"), m_repairScopeCombo);
    formLayout->addRow(QString::fromUtf8("Popis pro AI:"), m_descriptionEdit);
    pageLayout->addWidget(formCard);

    // ── Photos card ───────────────────────────────────────────────────────────
    auto *photosCard = new QFrame();
    photosCard->setObjectName("detailCard");
    auto *photosLayout = new QVBoxLayout(photosCard);
    photosLayout->setContentsMargins(16, 16, 16, 16);
    photosLayout->setSpacing(10);

    auto *photosTitle = new QLabel(QString::fromUtf8("V\u00fdb\u011br fotografii"));
    photosTitle->setObjectName("subSectionTitle");
    m_selectPhotosButton = new QPushButton(QString::fromUtf8("Vybrat fotografie z disku"));
    m_photoCountLabel = new QLabel(QString::fromUtf8("Zat\u00edm \u017e\u00e1dn\u00e9 fotografie."));
    m_photoCountLabel->setObjectName("hintLabel");

    m_thumbnailScrollArea = new QScrollArea();
    m_thumbnailScrollArea->setFixedHeight(kThumbSize + 24);
    m_thumbnailScrollArea->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    m_thumbnailScrollArea->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    m_thumbnailScrollArea->setWidgetResizable(false);
    m_thumbnailScrollArea->setFrameShape(QFrame::NoFrame);
    m_thumbnailScrollArea->setVisible(false);

    m_thumbnailStripWidget = new QWidget();
    m_thumbnailStripLayout = new QHBoxLayout(m_thumbnailStripWidget);
    m_thumbnailStripLayout->setContentsMargins(0, 0, 0, 0);
    m_thumbnailStripLayout->setSpacing(8);
    m_thumbnailScrollArea->setWidget(m_thumbnailStripWidget);

    auto *selectHint = new QLabel(QString::fromUtf8(
        "Kliknut\u00edm na n\u00e1hled vyberte hlavn\u00ed fotografii (reference pro AI). Prvn\u00ed je vybr\u00e1na automaticky."));
    selectHint->setObjectName("hintLabel");
    selectHint->setWordWrap(true);

    photosLayout->addWidget(photosTitle);
    photosLayout->addWidget(m_selectPhotosButton);
    photosLayout->addWidget(m_photoCountLabel);
    photosLayout->addWidget(m_thumbnailScrollArea);
    photosLayout->addWidget(selectHint);
    pageLayout->addWidget(photosCard);

    // ── Preview / overlay card ────────────────────────────────────────────────
    auto *previewCard = new QFrame();
    previewCard->setObjectName("detailCard");
    auto *previewLayout = new QVBoxLayout(previewCard);
    previewLayout->setContentsMargins(16, 16, 16, 16);
    previewLayout->setSpacing(10);

    auto *previewTitle = new QLabel(
        QString::fromUtf8("N\u00e1hled a oblast opravy (voliteln\u00e9)"));
    previewTitle->setObjectName("subSectionTitle");

    auto *overlayControlsRow = new QHBoxLayout();
    overlayControlsRow->setSpacing(8);
    auto *overlayLabel = new QLabel(QString::fromUtf8("Oblast opravy:"));
    overlayLabel->setObjectName("hintLabel");
    m_overlayModeViewButton = new QPushButton(QString::fromUtf8("Prohl\u00ed\u017eet"));
    m_overlayModeViewButton->setObjectName("overlayModeActive");
    m_overlayModeRectButton = new QPushButton(QString::fromUtf8("Obd\u00e9ln\u00edk"));
    m_overlayModePolyButton = new QPushButton(QString::fromUtf8("Polygon"));
    m_overlayAreaEdit = new QLineEdit();
    m_overlayAreaEdit->setPlaceholderText(QString::fromUtf8("Upřesněná plocha (m²)"));
    m_overlayAreaEdit->setFixedWidth(160);
    overlayControlsRow->addWidget(overlayLabel);
    overlayControlsRow->addWidget(m_overlayModeViewButton);
    overlayControlsRow->addWidget(m_overlayModeRectButton);
    overlayControlsRow->addWidget(m_overlayModePolyButton);
    overlayControlsRow->addWidget(m_overlayAreaEdit);
    overlayControlsRow->addStretch();

    m_overlayWidget = new ImageOverlayWidget();
    m_overlayWidget->setMinimumHeight(360);
    m_overlayWidget->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
    m_overlayWidget->setPlaceholder(QString::fromUtf8("Vyberte fotografie pro zobrazen\u00ed n\u00e1hledu."));

    previewLayout->addWidget(previewTitle);
    previewLayout->addLayout(overlayControlsRow);
    previewLayout->addWidget(m_overlayWidget);
    pageLayout->addWidget(previewCard);

    // ── Status / error ────────────────────────────────────────────────────────
    m_errorLabel = new QLabel();
    m_errorLabel->setObjectName("errorLabel");
    m_errorLabel->setWordWrap(true);
    m_errorLabel->hide();
    m_statusLabel = new QLabel();
    m_statusLabel->setObjectName("hintLabel");
    m_statusLabel->setWordWrap(true);
    m_statusLabel->hide();
    pageLayout->addWidget(m_errorLabel);
    pageLayout->addWidget(m_statusLabel);
    pageLayout->addStretch();

    // ── Connections ───────────────────────────────────────────────────────────
    connect(backButton, &QPushButton::clicked, this, &NewCaseView::cancelled);
    connect(m_selectPhotosButton, &QPushButton::clicked, this, &NewCaseView::selectPhotos);
    connect(m_submitButton, &QPushButton::clicked, this, &NewCaseView::submit);

    connect(m_overlayModeViewButton, &QPushButton::clicked, this, [this]() {
        m_overlayWidget->setMode(ImageOverlayWidget::Mode::View);
        m_overlayModeViewButton->setObjectName("overlayModeActive");
        m_overlayModeRectButton->setObjectName("");
        m_overlayModePolyButton->setObjectName("");
        style()->unpolish(m_overlayModeViewButton);
        style()->unpolish(m_overlayModeRectButton);
        style()->unpolish(m_overlayModePolyButton);
        style()->polish(m_overlayModeViewButton);
        style()->polish(m_overlayModeRectButton);
        style()->polish(m_overlayModePolyButton);
    });
    connect(m_overlayModeRectButton, &QPushButton::clicked, this, [this]() {
        m_overlayWidget->setMode(ImageOverlayWidget::Mode::Rectangle);
        m_overlayModeViewButton->setObjectName("");
        m_overlayModeRectButton->setObjectName("overlayModeActive");
        m_overlayModePolyButton->setObjectName("");
        style()->unpolish(m_overlayModeViewButton);
        style()->unpolish(m_overlayModeRectButton);
        style()->unpolish(m_overlayModePolyButton);
        style()->polish(m_overlayModeViewButton);
        style()->polish(m_overlayModeRectButton);
        style()->polish(m_overlayModePolyButton);
    });
    connect(m_overlayModePolyButton, &QPushButton::clicked, this, [this]() {
        m_overlayWidget->setMode(ImageOverlayWidget::Mode::Polygon);
        m_overlayModeViewButton->setObjectName("");
        m_overlayModeRectButton->setObjectName("");
        m_overlayModePolyButton->setObjectName("overlayModeActive");
        style()->unpolish(m_overlayModeViewButton);
        style()->unpolish(m_overlayModeRectButton);
        style()->unpolish(m_overlayModePolyButton);
        style()->polish(m_overlayModeViewButton);
        style()->polish(m_overlayModeRectButton);
        style()->polish(m_overlayModePolyButton);
    });
}

void NewCaseView::reset()
{
    if (m_titleEdit) m_titleEdit->clear();
    if (m_addressEdit) m_addressEdit->clear();
    if (m_descriptionEdit) m_descriptionEdit->clear();
    if (m_repairScopeCombo) m_repairScopeCombo->setCurrentIndex(0);
    if (m_overlayAreaEdit) m_overlayAreaEdit->clear();
    if (m_overlayWidget) {
        m_overlayWidget->clearSelection();
        m_overlayWidget->setPlaceholder(
            QString::fromUtf8("Vyberte fotografie pro zobrazen\u00ed n\u00e1hledu."));
    }
    if (m_photoCountLabel) {
        m_photoCountLabel->setText(QString::fromUtf8("Zat\u00edm \u017e\u00e1dn\u00e9 fotografie."));
    }
    if (m_thumbnailScrollArea) m_thumbnailScrollArea->setVisible(false);
    if (m_errorLabel) m_errorLabel->hide();
    if (m_statusLabel) m_statusLabel->hide();
    if (m_submitButton) m_submitButton->setEnabled(false);

    // Clear thumbnails
    while (QLayoutItem *item = m_thumbnailStripLayout->takeAt(0)) {
        delete item->widget();
        delete item;
    }
    m_thumbnailButtons.clear();
    m_photoPaths.clear();
    m_preparedImages.clear();
    m_primaryIndex = 0;
}

void NewCaseView::selectPhotos()
{
    const auto paths = QFileDialog::getOpenFileNames(
        this,
        QString::fromUtf8("Vybrat fotografie"),
        QString(),
        "Obrazky (*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp)");

    if (paths.isEmpty()) return;

    m_photoPaths = paths;
    m_primaryIndex = 0;
    m_preparedImages.clear();

    if (m_statusLabel) {
        m_statusLabel->setText(QString::fromUtf8("Na\u010d\u00edt\u00e1m fotografie..."));
        m_statusLabel->show();
    }

    for (const auto &path : m_photoPaths) {
        auto prepared = prepareImage(path);
        m_preparedImages.push_back(std::move(prepared));
    }

    if (m_statusLabel) m_statusLabel->hide();

    updateThumbnailStrip();
    updatePrimaryPreview();

    if (m_submitButton) {
        m_submitButton->setEnabled(!m_photoPaths.isEmpty());
    }
}

void NewCaseView::updateThumbnailStrip()
{
    // Clear existing
    while (QLayoutItem *item = m_thumbnailStripLayout->takeAt(0)) {
        delete item->widget();
        delete item;
    }
    m_thumbnailButtons.clear();

    const int count = m_photoPaths.size();
    if (count == 0) {
        m_photoCountLabel->setText(QString::fromUtf8("Zat\u00edm \u017e\u00e1dn\u00e9 fotografie."));
        m_thumbnailScrollArea->setVisible(false);
        return;
    }

    m_photoCountLabel->setText(
        QString::fromUtf8("Vybr\u00e1no %1 fotografii.").arg(count));
    m_thumbnailScrollArea->setVisible(true);

    for (int i = 0; i < count; ++i) {
        QImageReader reader(m_photoPaths.at(i));
        reader.setAutoTransform(true);
        QImage img = reader.read();
        QPixmap thumb;
        if (!img.isNull()) {
            thumb = QPixmap::fromImage(
                img.scaled(kThumbSize, kThumbSize, Qt::KeepAspectRatio, Qt::SmoothTransformation));
        }

        auto *btn = new QPushButton();
        btn->setFixedSize(kThumbSize + 4, kThumbSize + 4);
        btn->setFlat(true);
        if (!thumb.isNull()) {
            btn->setIcon(QIcon(thumb));
            btn->setIconSize(QSize(kThumbSize, kThumbSize));
        }
        const int idx = i;
        connect(btn, &QPushButton::clicked, this, [this, idx]() {
            setThumbnailSelection(idx);
        });
        m_thumbnailButtons.append(btn);
        m_thumbnailStripLayout->addWidget(btn);
    }
    m_thumbnailStripLayout->addStretch();

    setThumbnailSelection(m_primaryIndex);

    const int totalWidth = count * (kThumbSize + 4 + 8);
    m_thumbnailStripWidget->setFixedWidth(qMax(totalWidth, 100));
}

void NewCaseView::setThumbnailSelection(int index)
{
    if (index < 0 || index >= m_thumbnailButtons.size()) return;
    m_primaryIndex = index;

    for (int i = 0; i < m_thumbnailButtons.size(); ++i) {
        const bool selected = (i == m_primaryIndex);
        m_thumbnailButtons.at(i)->setStyleSheet(
            selected
                ? "border: 3px solid #c97b3d; border-radius: 8px; background: #f4e3cf;"
                : "border: 1px solid #e6d4bc; border-radius: 8px; background: transparent;");
    }

    updatePrimaryPreview();
}

void NewCaseView::updatePrimaryPreview()
{
    if (m_photoPaths.isEmpty() || m_primaryIndex < 0 || m_primaryIndex >= m_photoPaths.size()) {
        m_overlayWidget->setPlaceholder(
            QString::fromUtf8("Vyberte fotografie pro zobrazen\u00ed n\u00e1hledu."));
        return;
    }

    QImageReader reader(m_photoPaths.at(m_primaryIndex));
    reader.setAutoTransform(true);
    const QImage img = reader.read();
    if (img.isNull()) {
        m_overlayWidget->setPlaceholder(QString::fromUtf8("Nepoda\u0159ilo se na\u010d\u00edst fotografii."));
        return;
    }

    m_overlayWidget->clearSelection();
    m_overlayWidget->setMode(ImageOverlayWidget::Mode::View);
    m_overlayWidget->setPhoto(QPixmap::fromImage(img));
}

void NewCaseView::submit()
{
    if (m_errorLabel) m_errorLabel->hide();

    const QString title = m_titleEdit ? m_titleEdit->text().trimmed() : QString();
    if (title.isEmpty()) {
        if (m_errorLabel) {
            m_errorLabel->setText(QString::fromUtf8("N\u00e1zev zak\u00e1zky je povinn\u00fd."));
            m_errorLabel->show();
        }
        return;
    }
    if (m_photoPaths.isEmpty()) {
        if (m_errorLabel) {
            m_errorLabel->setText(QString::fromUtf8("Vyberte alespo\u0148 jednu fotografii."));
            m_errorLabel->show();
        }
        return;
    }

    const QString address = m_addressEdit ? m_addressEdit->text().trimmed() : QString();
    const QString repairScope = m_repairScopeCombo
        ? m_repairScopeCombo->currentData().toString()
        : QString();
    const QString description = m_descriptionEdit ? m_descriptionEdit->text().trimmed() : QString();

    if (m_submitButton) m_submitButton->setEnabled(false);
    if (m_statusLabel) {
        m_statusLabel->setText(QString::fromUtf8("Vytv\u00e1\u0159\u00edm zak\u00e1zku..."));
        m_statusLabel->show();
    }

    ApiService api;
    QString errorMsg;

    // 1. Create case
    const QString caseId = api.createCase(title, address, repairScope, description, &errorMsg);
    if (ApiService::sessionExpired()) { emit sessionExpired(); return; }
    if (caseId.isEmpty()) {
        if (m_errorLabel) {
            m_errorLabel->setText(errorMsg.isEmpty()
                ? QString::fromUtf8("Nepoda\u0159ilo se vytvo\u0159it zak\u00e1zku.")
                : errorMsg);
            m_errorLabel->show();
        }
        if (m_statusLabel) m_statusLabel->hide();
        if (m_submitButton) m_submitButton->setEnabled(true);
        return;
    }

    // 2. Upload photos
    if (m_statusLabel) {
        m_statusLabel->setText(
            QString::fromUtf8("Nahr\u00e1v\u00e1m %1 fotografii...").arg(m_preparedImages.size()));
    }

    // Put primary photo first
    std::vector<UploadImageDto> orderedImages = m_preparedImages;
    if (m_primaryIndex > 0 && m_primaryIndex < static_cast<int>(orderedImages.size())) {
        std::rotate(orderedImages.begin(),
                    orderedImages.begin() + m_primaryIndex,
                    orderedImages.end());
    }

    if (!api.uploadCaseImages(caseId, orderedImages, &errorMsg)) {
        if (ApiService::sessionExpired()) { emit sessionExpired(); return; }
        if (m_errorLabel) {
            m_errorLabel->setText(errorMsg.isEmpty()
                ? QString::fromUtf8("Nepoda\u0159ilo se nahr\u00e1t fotografie.")
                : errorMsg);
            m_errorLabel->show();
        }
        if (m_statusLabel) m_statusLabel->hide();
        if (m_submitButton) m_submitButton->setEnabled(true);
        return;
    }

    // 3. Trigger analysis
    if (m_statusLabel) {
        m_statusLabel->setText(QString::fromUtf8("Spu\u0161t\u011bm anal\u00fdzu AI..."));
    }

    const QString jobId = api.triggerAnalysisJob(caseId, &errorMsg);
    if (ApiService::sessionExpired()) { emit sessionExpired(); return; }
    // Analysis trigger failure is non-fatal — case was created and photos uploaded
    if (jobId.isEmpty() && !errorMsg.isEmpty()) {
        if (m_statusLabel) {
            m_statusLabel->setText(
                QString::fromUtf8("Zak\u00e1zka vytvo\u0159ena, anal\u00fdza se spust\u00ed automaticky."));
        }
    }

    if (m_statusLabel) m_statusLabel->hide();
    emit caseCreated(caseId);
}
