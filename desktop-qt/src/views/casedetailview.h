#pragma once

#include <QByteArray>
#include <QPixmap>
#include <QString>
#include <QStringList>
#include <QWidget>
#include <vector>

#include "dto/casedto.h"
#include "dto/imagedto.h"
#include "dto/uploadimagedto.h"

class QLabel;
class QLineEdit;
class QHBoxLayout;
class QListWidget;
class QPlainTextEdit;
class QPushButton;
class QResizeEvent;
class QScrollArea;
class QTimer;
class QIcon;

class CaseDetailView : public QWidget
{
    Q_OBJECT

public:
    explicit CaseDetailView(QWidget *parent = nullptr);
    void setCase(const QString &caseId);
    void clearCase();

signals:
    void caseDuplicated(const QString &newCaseId);
    void caseSent(const QString &sentCaseId);
    void newVariantRequested(const QString &caseId);

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
    [[nodiscard]] bool refreshImagesFromBackend(QString *errorMessage = nullptr);
    void setPrimaryImagePreview(const QPixmap &pixmap);
    void setPrimaryImagePlaceholder(const QString &message);
    void updatePrimaryImagePreview();
    void showImagePreview(const ImageDto *image);
    [[nodiscard]] const ImageDto *selectedImage() const;
    void resizeEvent(QResizeEvent *event) override;

    QLabel *m_titleLabel = nullptr;
    QLabel *m_subtitleLabel = nullptr;
    QLabel *m_statusValueLabel = nullptr;
    QLabel *m_addressValueLabel = nullptr;
    QLabel *m_scopeValueLabel = nullptr;
    QLabel *m_areaValueLabel = nullptr;
    QLabel *m_proposalStatusValueLabel = nullptr;
    QLabel *m_referenceTestContextLabel = nullptr;
    QLineEdit *m_proposalSubjectEdit = nullptr;
    QPlainTextEdit *m_proposalSummaryEdit = nullptr;
    QLineEdit *m_proposalMaterialCostEdit = nullptr;
    QLineEdit *m_proposalLaborCostEdit = nullptr;
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
    QLabel *m_errorLabel = nullptr;
    QLabel *m_primaryImageLabel = nullptr;
    QLabel *m_primaryImagePreviewLabel = nullptr;
    QLabel *m_imageHintLabel = nullptr;
    QScrollArea *m_thumbnailScrollArea = nullptr;
    QWidget *m_thumbnailStripWidget = nullptr;
    QHBoxLayout *m_thumbnailStripLayout = nullptr;
    QListWidget *m_proposalWorkItemsList = nullptr;
    QListWidget *m_proposalMaterialsList = nullptr;
    QLabel *m_pendingLocalImagesLabel = nullptr;
    QListWidget *m_pendingLocalImagesList = nullptr;
    QPushButton *m_setPrimaryButton = nullptr;
    QPushButton *m_setAnalysisReferenceButton = nullptr;
    QPushButton *m_moveUpButton = nullptr;
    QPushButton *m_moveDownButton = nullptr;
    QPushButton *m_addImagesButton = nullptr;
    QPushButton *m_convertImagesButton = nullptr;
    QPushButton *m_uploadImagesButton = nullptr;
    QPushButton *m_saveProposalButton = nullptr;
    QPushButton *m_createFinalProposalButton = nullptr;
    QPushButton *m_saveAsButton = nullptr;
    QPushButton *m_newVariantButton = nullptr;
    QPushButton *m_sendCaseButton = nullptr;
    QPixmap m_primaryImagePixmap;
    std::vector<ImageDto> m_images;
    std::vector<QPushButton *> m_thumbnailButtons;
    QString m_caseId;
    QString m_selectedImageId;
    bool m_isReferenceDataset = false;
    QString m_expectedScope;
    QString m_currentRepairScope;
    QStringList m_currentProposalWorkItems;
    QStringList m_currentProposalMaterials;
    QString m_expectedPrimaryFilename;
    QString m_expectedAnalysisReferenceFilename;
    QString m_referenceSourcePage;
    QStringList m_pendingLocalImagePaths;
    std::vector<LocalPreparedImage> m_preparedLocalImages;
    QTimer *m_imagePollingTimer = nullptr;
    int m_remainingImagePollAttempts = 0;
};
