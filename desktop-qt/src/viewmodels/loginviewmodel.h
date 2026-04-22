#pragma once

#include <QObject>

#include "dto/logindto.h"

class LoginViewModel : public QObject
{
    Q_OBJECT
public:
    explicit LoginViewModel(QObject *parent = nullptr);

    [[nodiscard]] LoginDto initialState() const;
    [[nodiscard]] bool canLogin(const LoginDto &state) const;
};
