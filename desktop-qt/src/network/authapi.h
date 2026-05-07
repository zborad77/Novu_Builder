#pragma once

#include "apiclient.h"
#include "models/loginresultdto.h"

class AuthApi : public ApiClient
{
public:
    using ApiClient::ApiClient;

    [[nodiscard]] LoginResultDto login(
        const QString &email,
        const QString &password,
        QString *errorMessage = nullptr) const;
};
