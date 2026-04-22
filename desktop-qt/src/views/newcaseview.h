#pragma once

#include <QByteArray>
#include <QPixmap>
#include <QString>
#include <QStringList>
#include <QWidget>
#include <vector>

#include "dto/uploadimagedto.h"
#include "widgets/imageoverlaywidget.h"
#include "widgets/viewerstate.h"

class ApiService;
class QComboBox;
class QLabel;
class QLineEdit;
class QHBoxLayout;
class QPlainTextEdit;
class QPushButton;
class QScrollArea;
class SessionService;

class NewCaseView : public QWidget
{
    Q_OBJECT

public:
    explicit NewCaseView(SessionService &session, QWidget *parent = nullptr);

    void reset();

signals:
    void caseCreated(const QString &caseId);
    void cancelled();
    void sessionExpired();

private:
    void selectPhotos();
    void updateThumbnailStrip();
    void setThumbnailSelection(int index);
    void updatePrimaryPreview();
    void submit();

    // Form
    QLineEdit *m_titleEdit = nullptr;
    QLineEdit *m_addressEdit = nullptr;
    QComboBox *m_repairScopeCombo = nullptr;
    QLineEdit *m_descriptionEdit = nullptr;

    // Photos
    QPushButton *m_selectPhotosButton = nullptr;
    QLabel *m_photoCountLabel = nullptr;
    QScrollArea *m_thumbnailScrollArea = nullptr;
    QWidget *m_thumbnailStripWidget = nullptr;
    QHBoxLayout *m_thumbnailStripLayout = nullptr;

    // Preview / overlay
    ImageOverlayWidget *m_overlayWidget = nullptr;
    ViewerState m_overlayViewerState;
    QPushButton *m_overlayModeViewButton = nullptr;
    QPushButton *m_overlayModeRectButton = nullptr;
    QPushButton *m_overlayModePolyButton = nullptr;
    QLineEdit *m_overlayAreaEdit = nullptr;

    // Status / actions
    QLabel *m_errorLabel = nullptr;
    QLabel *m_statusLabel = nullptr;
    QPushButton *m_submitButton = nullptr;

    // Data
    ApiService *m_apiService = nullptr;
    QStringList m_photoPaths;
    int m_primaryIndex = 0;
    QList<QPushButton *> m_thumbnailButtons;
    std::vector<UploadImageDto> m_preparedImages;
};
