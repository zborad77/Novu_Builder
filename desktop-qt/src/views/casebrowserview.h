#pragma once

#include <QWidget>
#include <vector>
#include "dto/casedto.h"

class QLabel;
class QScrollArea;
class QVBoxLayout;

class CaseBrowserView : public QWidget
{
    Q_OBJECT

public:
    enum class Mode { WorkCases, HistoryCases };

    explicit CaseBrowserView(QWidget *parent = nullptr);
    void loadCases(Mode mode);

signals:
    void caseOpenRequested(const QString &caseId, bool readOnly);
    void sessionExpired();

private:
    void buildCards(const std::vector<CaseDto> &cases, Mode mode);

    QLabel *m_titleLabel = nullptr;
    QLabel *m_subtitleLabel = nullptr;
    QLabel *m_statusLabel = nullptr;
    QVBoxLayout *m_cardsLayout = nullptr;
    QWidget *m_cardsContainer = nullptr;
};
