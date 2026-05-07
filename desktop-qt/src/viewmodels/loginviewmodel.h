#pragma once

#include "models/logindto.h"

class LoginViewModel
{
public:
    [[nodiscard]] LoginDto initialState() const;
    [[nodiscard]] bool canLogin(const LoginDto &state) const;
};
