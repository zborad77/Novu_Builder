#pragma once

#include <QByteArray>
#include <QEvent>
#include <QPixmap>
#include <QString>
#include <QStringList>
#include <QWidget>
#include <vector>

#include "models/casedto.h"
#include "models/imagedto.h"
#include "models/uploadimagedto.h"
#include "ui/widgets/imageoverlaywidget.h"

class QLabel;
class QLineEdit;
class QHBoxLayout;
class QListWidget;
class QPlainTextEdit;
class QPushButton;
class QResizeEvent;
class QScrollArea;
class QTabWidget;
class QTimer;
class QIcon;

class CaseDetailView : public QWidget
{
    Q_OBJECT

public:
    explicit CaseDetailView(QWidget *parent = nullptr);
    void setCase(const QString &caseId);
    void clearCase();
    void switchToPhotosTab();
    void navigateToField(const QString &fieldKey);
    void triggerSave();
    [[nodiscard]] bool hasUnsavedChanges() const;
    [[nodiscard]] QString caseSource() const;
    void setReadOnly(bool readOnly);

signals:
    void caseDuplicated(const QString &newCaseId);
    void caseSent(const QString &sentCaseId);
    void newVariantRequested(const QString &caseId);
    void sessionExpired();

private:
    enum class LocalImageState
    {
        PendingConversion,
        ReadyToUpload,
        Uploading,
        Uploaded,
        Error,
    };

    struct LocalPreparedImage
    {
        QString sourcePath;
        QString outputFilename;
        QString mimeType;
        int width = 0;
        int height = 0;
        int byteSize = 0;
        LocalImageState state = LocalImageState::PendingConversion;
        QString errorMessage;
        QByteArray payload;
    };

    void updateImagesPanel();
    void updateImageActionButtons();
    void updateReferenceTestContextLabel();
    void updateThumbnailSelectionState();
    void setSelectedImageById(const QString &imageId, bool autoPromoteToPrimary = true);
    void setImageHintMessage(const QString &message, bool isError = false);
    void applyCaseData(const CaseDto &caseDto);
    void selectAdjacentImage(int step);
    void autoSetDisplayedImageAsPrimary();
    void selectLocalImages();
    void convertPendingLocalImages();
    void uploadPreparedLocalImages();
    void updatePendingLocalImagesPanel();
    void setSelectedImageAsPrimary();
    void setSelectedImageAsAnalysisReference();
    void saveProposalDraft();
    void createFinalProposal();
    void duplicateCase(const QString &mode);
    void sendCurrentCase();
    void startImageStatusPolling();
    void stopImageStatusPolling();
    void pollImageStatuses();
    void triggerAnalysis();
    void confirmSelectionArea();
    void startAnalysisPolling(const QString &jobId);
    void stopAnalysisPolling();
    void pollAnalysisStatus();
    void downloadExport(const QString &exportType);
    void exportAsZip();
    [[nodiscard]] bool refreshImagesFromBackend(QString *errorMessage = nullptr);
    void setPrimaryImagePreview(const QPixmap &pixmap);
    void setPrimaryImagePlaceholder(const QString &message);
    void updatePrimaryImagePreview();
    void showImagePreview(const ImageDto *image);
    [[nodiscard]] const ImageDto *selectedImage() const;
    void resizeEvent(QResizeEvent *event) override;
    bool eventFilter(QObject *watched, QEvent *event) override;

    QLabel *m_titleLabel = nullptr;
    QLabel *m_subtitleLabel = nullptr;
    QLabel *m_statusValueLabel = nullptr;
    QLabel *m_addressValueLabel = nullptr;
    QLabel *m_scopeValueLabel = nullptr;
    QLabel *m_areaValueLabel = nullptr;
    QLabel *m_proposalStatusValueLabel = nullptr;
    QLabel *m_workflowStatusValueLabel = nullptr;
    QLabel *m_workflowBlockingReasonsValueLabel = nullptr;
    QLabel *m_referenceTestContextLabel = nullptr;
    QLineEdit *m_proposalSubjectEdit = nullptr;
    QPlainTextEdit *m_proposalSummaryEdit = nullptr;
    QLineEdit *m_proposalMaterialCostEdit = nullptr;
    QLineEdit *m_proposalLaborCostEdit = nullptr;
    QLineEdit *m_proposalTransportCostEdit = nullptr;
    QLineEdit *m_proposalAmortizationEdit = nullptr;
    QLineEdit *m_proposalMarginEdit = nullptr;
    QLabel *m_proposalTotalValueLabel = nullptr;
    QLineEdit *m_proposalSupplierEdit = nullptr;
    QLineEdit *m_proposalCompanyEdit = nullptr;
    QLabel *m_finalProposalStatusValueLabel = nullptr;
    QLabel *m_finalProposalVersionValueLabel = nullptr;
    QLabel *m_finalProposalSubjectValueLabel = nullptr;
    QLabel *m_finalProposalSummaryValueLabel = nullptr;
    QLabel *m_finalProposalTotalValueLabel = nullptr;
    // Analysis / Findings
    QLabel *m_analysisObjectTypeLabel = nullptr;
    QLabel *m_analysisAreaLabel = nullptr;
    QLabel *m_analysisSurfaceConditionLabel = nullptr;
    QLabel *m_analysisRecommendedScopeLabel = nullptr;
    QLabel *m_analysisDurationLabel = nullptr;
    QListWidget *m_analysisWorkflowList = nullptr;
    QListWidget *m_analysisMaterialsList = nullptr;
    // Quote variants
    QLabel *m_quoteEconomyValueLabel = nullptr;
    QLabel *m_quoteStandardValueLabel = nullptr;
    QLabel *m_quotePremiumValueLabel = nullptr;
    QTabWidget *m_tabWidget = nullptr;
    QPushButton *m_runAnalysisButton = nullptr;
    ImageOverlayWidget *m_overlayWidget = nullptr;
    QPushButton *m_overlayModeViewButton = nullptr;
    QPushButton *m_overlayModeRectButton = nullptr;
    QPushButton *m_overlayModePolyButton = nullptr;
    QPushButton *m_overlayConfirmButton = nullptr;
    QLineEdit *m_overlayAreaEdit = nullptr;
    QLabel *m_errorLabel = nullptr;
    QLabel *m_primaryImageLabel = nullptr;
    QLabel *m_primaryImagePreviewLabel = nullptr;
    QLabel *m_imageHintLabel = nullptr;
    QScrollArea *m_thumbnailScrollArea = nullptr;
    QWidget *m_thumbnailStripWidget = nullptr;
    QHBoxLayout *m_thumbnailStripLayout = nullptr;
    QLabel *m_proposalWorkItemsList = nullptr;
    QListWidget *m_proposalMaterialsList = nullptr;
    QLabel *m_pendingLocalImagesLabel = nullptr;
    QListWidget *m_pendingLocalImagesList = nullptr;
    QPushButton *m_setPrimaryButton = nullptr;
    QPushButton *m_setAnalysisReferenceButton = nullptr;
    QPushButton *m_moveUpButton = nullptr;
    QPushButton *m_moveDownButton = nullptr;
    QPushButton *m_addImagesButton = nullptr;
    QPushButton *m_convertImagesButton = nullptr;
    QPushButton *m_saveProposalButton = nullptr;
    QPushButton *m_createFinalProposalButton = nullptr;
    QPushButton *m_downloadDraftDocxButton = nullptr;
    QPushButton *m_downloadQuoteDocxButton = nullptr;
    QPushButton *m_downloadQuotePdfButton = nullptr;
    QPushButton *m_exportZipButton = nullptr;
    QPushButton *m_saveAsButton = nullptr;
    QPushButton *m_newVariantButton = nullptr;
    QPushButton *m_sendCaseButton = nullptr;
    QPixmap m_primaryImagePixmap;
    std::vector<ImageDto> m_images;
    std::vector<QPushButton *> m_thumbnailButtons;
    CaseDto m_currentCase;
    QString m_caseId;
    QString m_analysisId;
    QString m_selectedImageId;
    bool m_isReferenceDataset = false;
    QString m_expectedScope;
    QString m_currentRepairScope;
    QStringList m_currentProposalWorkItems;
    QStringList m_currentProposalMaterials;
    QList<CaseDto::ProposalMaterialItem> m_currentProposalMaterialItems;
    QString m_expectedPrimaryFilename;
    QString m_expectedAnalysisReferenceFilename;
    QString m_referenceSourcePage;
    QStringList m_pendingLocalImagePaths;
    std::vector<LocalPreparedImage> m_preparedLocalImages;
    QTimer *m_imagePollingTimer = nullptr;
    int m_remainingImagePollAttempts = 0;
    QTimer *m_analysisPollingTimer = nullptr;
    int m_remainingAnalysisPollAttempts = 0;
    QString m_analysisJobId;
    QLabel *m_analysisJobStatusLabel = nullptr;
    QString m_source; // "mobile" | "desktop"
    bool m_isDirty = false;
    bool m_isReadOnly = false;
    QLabel *m_readOnlyBanner = nullptr;
    QPushButton *m_editUnlockButton = nullptr;
    // Přehled dashboard
    QLabel *m_dashPhotoLabel = nullptr;
    QLabel *m_dashObjTypeLabel = nullptr;
    QLabel *m_dashAreaLabel = nullptr;
    QLabel *m_dashSurfaceLabel = nullptr;
    QLabel *m_dashScopeLabel = nullptr;
    QLabel *m_dashDurationLabel = nullptr;
    QLabel *m_dashLaborLabel = nullptr;
    QLabel *m_dashMaterialLabel = nullptr;
    QLabel *m_dashTransportLabel = nullptr;
    QLabel *m_dashMarginLabel = nullptr;
    QLabel *m_dashTotalLabel = nullptr;
    QListWidget *m_dashWorkflowList = nullptr;
    QPushButton *m_dashRunAnalysisButton = nullptr;
};
