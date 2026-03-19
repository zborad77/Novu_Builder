#pragma once

#include <QByteArray>
#include <QString>
#include <vector>

#include "dto/casedto.h"
#include "dto/imagedto.h"
#include "dto/proposaldraftpatchdto.h"
#include "dto/uploadimagedto.h"

class ApiService
{
public:
    explicit ApiService(QString baseUrl = "http://127.0.0.1:8000/api/v1");

    [[nodiscard]] QString baseUrl() const;
    [[nodiscard]] std::vector<CaseDto> fetchCases(QString *errorMessage = nullptr) const;
    [[nodiscard]] QString duplicateCase(
        const QString &caseId,
        const QString &mode,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] bool sendCase(const QString &caseId, QString *errorMessage = nullptr) const;
    [[nodiscard]] CaseDto fetchCaseDetail(const QString &caseId, QString *errorMessage = nullptr) const;
    [[nodiscard]] CaseDto updateCaseProposalDraft(
        const QString &caseId,
        const ProposalDraftPatchDto &proposalDraft,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] CaseDto createCaseFinalProposal(const QString &caseId, QString *errorMessage = nullptr) const;
    [[nodiscard]] std::vector<ImageDto> fetchCaseImages(const QString &caseId, QString *errorMessage = nullptr) const;
    [[nodiscard]] std::vector<ImageDto> moveCaseImage(
        const QString &caseId,
        const QString &imageId,
        const QString &direction,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] bool setCasePrimaryImage(
        const QString &caseId,
        const QString &imageId,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] bool setCaseAnalysisReferenceImage(
        const QString &caseId,
        const QString &imageId,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] bool uploadCaseImages(
        const QString &caseId,
        const std::vector<UploadImageDto> &images,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] QByteArray fetchImageData(const QString &imageUrl, QString *errorMessage = nullptr) const;

private:
    QString m_baseUrl;
};
